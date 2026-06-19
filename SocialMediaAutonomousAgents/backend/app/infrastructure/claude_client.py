"""Thin Anthropic Messages API wrapper (Claude)."""

from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Per-run accumulated LLM cost in USD. The cost wrapper (cost_meter) reads + resets it.
_run_llm_cost_usd: contextvars.ContextVar[float] = contextvars.ContextVar(
    "_run_llm_cost_usd", default=0.0
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    t = text.strip()
    m = _JSON_FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        try:
            out = json.loads(t[start : end + 1])
            return out if isinstance(out, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class ClaudeClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = (api_key or settings.anthropic_api_key or "").strip()
        self._model = (model or settings.claude_model or "claude-sonnet-4-6").strip()

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def messages(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2048,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("ClaudeClient: ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install the anthropic package to use ClaudeClient") from exc
        client = anthropic.Anthropic(api_key=self._api_key)
        msg = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Record token usage into per-run accumulator
        _record_usage(getattr(msg, "usage", None))
        parts: list[str] = []
        for block in msg.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts).strip()

    def messages_json_dict(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2048,
    ) -> dict[str, Any] | None:
        raw = self.messages(system=system, user=user, max_tokens=max_tokens)
        parsed = _extract_json_object(raw)
        if parsed is None:
            logger.warning("ClaudeClient: could not parse JSON from model output")
        return parsed

    def messages_multi(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> str:
        """Call Claude with a native multi-turn messages array instead of a single user string."""
        if not self.enabled:
            raise RuntimeError("ClaudeClient: ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install the anthropic package to use ClaudeClient") from exc
        client = anthropic.Anthropic(api_key=self._api_key)
        msg = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        _record_usage(getattr(msg, "usage", None))
        parts: list[str] = []
        for block in msg.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts).strip()

    def messages_json_dict_multi(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> dict[str, Any] | None:
        """Multi-turn variant of messages_json_dict."""
        raw = self.messages_multi(system=system, messages=messages, max_tokens=max_tokens)
        parsed = _extract_json_object(raw)
        if parsed is None:
            logger.warning("ClaudeClient: could not parse JSON from model output")
        return parsed


_claude: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    global _claude
    if _claude is None:
        _claude = ClaudeClient()
    return _claude


def _tokens_to_usd(input_tokens: int, output_tokens: int) -> float:
    """Convert tokens to USD via the ONE configurable blended rate.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Cost in USD using settings.cost_per_1k_tokens_usd as the blended rate.
    """
    total = (input_tokens or 0) + (output_tokens or 0)
    return total / 1000.0 * settings.cost_per_1k_tokens_usd


def _record_usage(usage: Any) -> None:
    """Record token usage into the per-run accumulator.

    Args:
        usage: The SDK response.usage object with input_tokens and output_tokens.
    """
    if usage is None:
        return
    cost = _tokens_to_usd(
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
    )
    _run_llm_cost_usd.set(_run_llm_cost_usd.get() + cost)


def drain_run_llm_cost_usd() -> float:
    """Read and zero the accumulated LLM cost since the last drain.

    Called by the cost wrapper in the engine to tally per-leaf spend.

    Returns:
        The accumulated cost in USD since the last drain.
    """
    v = _run_llm_cost_usd.get()
    _run_llm_cost_usd.set(0.0)
    return v

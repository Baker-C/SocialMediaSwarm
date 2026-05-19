"""Thin Anthropic Messages API wrapper (Claude)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

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


_claude: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    global _claude
    if _claude is None:
        _claude = ClaudeClient()
    return _claude

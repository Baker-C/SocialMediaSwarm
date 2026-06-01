from __future__ import annotations

import logging
import re

from app.agents.base_agent import BaseAgent
from app.interval_crew import prompt_loader
from app.infrastructure.claude_client import get_claude_client

logger = logging.getLogger(__name__)

# Legacy fallback signature (must not ship to X)
_FALLBACK_MARKERS = ("#automation", "angle 1", "angle 2", "angle 3")
_JSON_LEAK_MARKERS = ('"account_id"', '"profile"', '"post_engagements"', '"niche_context"')
_NICHE_REJECT = "niche_mismatch"


class SafetyGuardian(BaseAgent):
    def run(self):
        return "safe"

    def evaluate(self, content: str, *, niche: str | None = None) -> tuple[bool, str | None]:
        text = content.strip()
        if len(text) < 10:
            return False, "too_short"
        if len(text) > 300:
            return False, "too_long"
        leak = self._looks_like_prompt_leak(text)
        if leak:
            return False, leak
        niche_reason = self._check_niche_fit(text, niche)
        if niche_reason:
            return False, niche_reason
        return True, None

    def _check_niche_fit(self, text: str, niche: str | None) -> str | None:
        """Return reject reason when the post topic does not fit the account niche."""
        label = (niche or "").strip()
        if not label:
            return None

        claude = get_claude_client()
        if not claude.enabled:
            logger.warning("SafetyGuardian: skipping niche check (Claude disabled)")
            return None

        try:
            system = prompt_loader.load("tasks/niche_fit_check.system.md")
            user = prompt_loader.load_template(
                "tasks/niche_fit_check.user.md",
                niche=label,
                post_text=text[:2500],
            )
            data = claude.messages_json_dict(system=system, user=user, max_tokens=256)
        except Exception as exc:
            logger.warning("SafetyGuardian niche check failed: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        fits = data.get("fits_niche")
        if fits is True or str(fits).lower() == "true":
            return None

        reason = str(data.get("reason") or "off-topic for niche").strip()
        detail = f"{_NICHE_REJECT}:{reason}"[:200]
        logger.info("SafetyGuardian niche reject niche=%s reason=%s", label, reason)
        return detail

    @staticmethod
    def _looks_like_prompt_leak(text: str) -> str | None:
        t = text.strip()
        if t.startswith("{") or t.startswith("["):
            return "prompt_json_leak"
        lower = t.lower()
        for marker in _JSON_LEAK_MARKERS:
            if marker in lower:
                return "prompt_json_leak"
        for marker in _FALLBACK_MARKERS:
            if marker in lower:
                return "fallback_template_leak"
        if t.count('"') >= 6 and t.count(":") >= 4:
            return "structured_data_leak"
        if re.search(r'\{\s*"account"', t):
            return "prompt_json_leak"
        return None


def is_niche_mismatch_reject(reason: str | None) -> bool:
    return bool(reason and reason.startswith(_NICHE_REJECT))

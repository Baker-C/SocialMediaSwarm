from __future__ import annotations

import re

from app.agents.base_agent import BaseAgent

# Legacy fallback signature (must not ship to X)
_FALLBACK_MARKERS = ("#automation", "angle 1", "angle 2", "angle 3")
_JSON_LEAK_MARKERS = ('"account_id"', '"profile"', '"post_engagements"', '"niche_context"')


class SafetyGuardian(BaseAgent):
    def run(self):
        return "safe"

    def evaluate(self, content: str) -> tuple[bool, str | None]:
        text = content.strip()
        if len(text) < 10:
            return False, "too_short"
        if len(text) > 300:
            return False, "too_long"
        leak = self._looks_like_prompt_leak(text)
        if leak:
            return False, leak
        return True, None

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

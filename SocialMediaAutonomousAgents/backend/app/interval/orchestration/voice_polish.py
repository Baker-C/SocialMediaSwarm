"""Deterministic punctuation polish applied after generation, before posting.

Pure & parameterized: callers pass the account's punctuation rules; there is no
module-level rule state. This module ONLY normalizes punctuation/whitespace.
Voice/persona steering (banned phrases, contrast tells, casual caps) is handled
at generation time via the soul's personality + contrast_patterns — not here.
(Historical banned-phrase list archived in docs/voice-banned-phrases-archive.md.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.account import PunctuationRule, default_punctuation_rules


@dataclass
class VoicePolishResult:
    original: str
    polished: str
    changed: bool
    notes: list[str] = field(default_factory=list)


def _coerce_rules(rules) -> list[dict]:
    """Accept list[PunctuationRule] | list[dict] | None → list[{pattern, replacement}].
    None/empty falls back to the shared defaults so a misconfigured account still
    gets basic hygiene (em-dash removal etc.)."""
    if not rules:
        return default_punctuation_rules()
    out: list[dict] = []
    for r in rules:
        if isinstance(r, PunctuationRule):
            out.append({"pattern": r.pattern, "replacement": r.replacement})
        elif isinstance(r, dict) and r.get("pattern"):
            out.append({"pattern": r["pattern"], "replacement": r.get("replacement")})
    return out or default_punctuation_rules()


def polish_text(text: str, rules=None) -> VoicePolishResult:
    """Apply punctuation auto-fixes to a single block of text (opinion or quip).
    Each rule: substitute `pattern`→`replacement`, or delete the match if replacement is None.
    Rules apply in order; later rules see earlier results (e.g. em-dash→', ' then collapse spaces)."""
    original = (text or "").strip()
    if not original:
        return VoicePolishResult(original="", polished="", changed=False)

    out = original
    notes: list[str] = []
    for rule in _coerce_rules(rules):
        repl = rule["replacement"]
        compiled = re.compile(rule["pattern"])
        new_out = compiled.sub("" if repl is None else repl, out)
        if new_out != out:
            notes.append(f"fix:{rule['pattern'][:40]}")
            out = new_out

    out = out.strip()
    return VoicePolishResult(original=original, polished=out, changed=out != original, notes=notes)


# Backwards-compatible name used by older imports; same behavior as polish_text.
def polish_post(text: str, rules=None) -> VoicePolishResult:
    return polish_text(text, rules)

"""Pick first safety-approved candidate that passes voice rules (soft-flag)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.hourly.orchestration.voice_polish import VOICE_SOFT_FLAG_PREFIX, polish_post

if TYPE_CHECKING:
    from app.agents.safety_guardian import SafetyGuardian


def select_polished_from_ranked(
    guardian: SafetyGuardian,
    ranked_candidates: list[str],
) -> tuple[str | None, str | None, dict | None]:
    """
    Return (polished_body, last_reject_reason, voice_trace).

    Tries ranked order: safety pass → auto-fix polish → soft-flag only if rules remain broken.
    """
    last_reject: str | None = None
    last_voice_trace: dict | None = None

    for body in ranked_candidates:
        approved, reason = guardian.evaluate(body)
        if not approved:
            last_reject = reason
            continue

        polish = polish_post(body)
        voice_trace = {
            "original": polish.original,
            "polished": polish.polished,
            "changed": polish.changed,
            "fixes": polish.notes,
            "violations": polish.violations,
            "soft_flag": polish.soft_flag,
        }
        last_voice_trace = voice_trace

        if polish.soft_flag:
            last_reject = f"{VOICE_SOFT_FLAG_PREFIX}:{','.join(polish.violations[:5])}"
            continue

        polished = polish.polished if polish.polished else body
        approved2, reason2 = guardian.evaluate(polished)
        if not approved2:
            last_reject = reason2
            continue

        return polished, last_reject, voice_trace

    return None, last_reject or "all_candidates_rejected", last_voice_trace

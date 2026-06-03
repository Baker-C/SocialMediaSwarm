"""Post-crew deterministic safety gate (not a Crew agent)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.interval.orchestration.voice_select import select_polished_from_ranked

if TYPE_CHECKING:
    from app.agents.safety_guardian import SafetyGuardian


def select_from_ranked(
    guardian: SafetyGuardian,
    ranked_candidates: list[str],
) -> tuple[str | None, str | None]:
    """Return (approved_body, last_reject_reason). Prefer voice_select when polish matters."""
    body, reject, _trace = select_polished_from_ranked(guardian, ranked_candidates)
    return body, reject

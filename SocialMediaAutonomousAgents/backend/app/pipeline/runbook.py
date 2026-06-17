"""Public runbook API — simple imports, readable execution."""

from __future__ import annotations

from app.pipeline.types.context import TickRunContext
from app.services.account_repository import current_interval_slot_key


def start(
    account_id: str,
    *,
    niche: str = "",
    mode: str = "scheduled",
    slot: str | None = None,
) -> TickRunContext:
    """Create a run context for one account."""
    return TickRunContext(
        account_id=account_id.strip(),
        slot=(slot or current_interval_slot_key()).strip(),
        mode=mode if mode in ("scheduled", "force") else "scheduled",
        niche=niche.strip(),
    )

"""Public runbook API — simple imports, readable execution."""

from __future__ import annotations

from app.pipeline._runbook_engine import RunbookResult, run_steps
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.services.deps import PostRunDeps
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


def reference_analysis(
    account_id: str,
    *,
    niche: str = "",
    mode: str = "scheduled",
    deps: PostRunDeps | None = None,
) -> RunbookResult:
    """Run the reference-analysis portion of the post runbook."""
    ctx = start(account_id, niche=niche, mode=mode)
    services = deps or PostRunDeps.build()
    return run_steps(POST_TICK_REFERENCE_STEPS, ctx, services)


# Readable re-export of step order (for docs, tests, force-post UI).
steps = POST_TICK_REFERENCE_STEPS

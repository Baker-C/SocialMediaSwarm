"""External timeline reference analysis (rank → pattern summary)."""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

SUBAGENT_ID = "timeline_reference_analyst"
SUBAGENT_PURPOSE = "Analyze top external timeline references for compose context"


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank top timeline references and produce a pattern brief (delegates to runbook steps)."""
    rank = steps.rank_external_references(ctx, deps)
    if not rank.ok and not rank.skipped:
        return rank
    return steps.brief_external_references(ctx, deps)

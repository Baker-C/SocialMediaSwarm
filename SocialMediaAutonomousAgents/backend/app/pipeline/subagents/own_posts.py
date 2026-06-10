"""Own-post performance analysis (rank → pattern summary)."""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

SUBAGENT_ID = "own_posts_reference_analyst"
SUBAGENT_PURPOSE = "Analyze top own posts for voice and success patterns"


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank top own posts and produce a voice/success brief (delegates to runbook steps)."""
    rank = steps.rank_own_posts(ctx, deps)
    if not rank.ok and not rank.skipped:
        return rank
    return steps.brief_own_posts(ctx, deps)

"""Readable runbook: ordered steps for reference analysis before compose.

Each entry is ``(step_id, callable)``. Callables take ``(ctx, deps)`` only.
"""

from __future__ import annotations

from collections.abc import Callable

from app.pipeline.services import steps
from app.pipeline.subagents import own_posts, timeline
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]

# The runbook — read top to bottom; this is the source of truth for step order.
POST_TICK_REFERENCE_STEPS: tuple[tuple[str, StepFn], ...] = (
    ("profile", steps.profile),
    ("timeline_pool", steps.timeline_pool),
    ("search_pool", steps.search_pool),
    ("merge_reference_pools", steps.merge_reference_pools),
    ("own_posts_pool", steps.own_posts_pool),
    ("timeline_analysis", timeline.run),
    ("own_posts_analysis", own_posts.run),
)

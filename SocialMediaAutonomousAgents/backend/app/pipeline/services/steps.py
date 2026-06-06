"""Thin step wrappers — hide tool argument wiring from the runbook."""

from __future__ import annotations

from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult


def profile(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    return tool_catalog().data.account_profile.run(ctx, tick_data=deps.tick_data)


def timeline_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    bundle = ctx.get("account_bundle") or {}
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    auth_id = str(prof.get("id")) if isinstance(prof, dict) and prof.get("id") is not None else None
    return tool_catalog().data.timeline_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        authenticated_user_id=auth_id,
    )


def own_posts_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")
    return tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)

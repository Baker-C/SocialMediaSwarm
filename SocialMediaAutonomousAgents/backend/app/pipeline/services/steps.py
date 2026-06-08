"""Thin step wrappers — hide tool argument wiring from the runbook."""

from __future__ import annotations

from app.core.config import settings
from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService


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


def _authenticated_user_id(ctx: TickRunContext) -> str | None:
    bundle = ctx.get("account_bundle") or {}
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    if isinstance(prof, dict) and prof.get("id") is not None:
        return str(prof["id"])
    return None


def search_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if not settings.trend_tweet_search_enabled:
        return StepResult(ok=True, skipped=True, skip_reason="search_disabled")
    acc = deps.repo.load(ctx.account_id)
    if acc is None:
        return StepResult(ok=False, skip_reason="account_not_found")
    queries = list(acc.search_queries or [])
    if not queries:
        return StepResult(ok=True, skipped=True, skip_reason="no_search_queries")
    return tool_catalog().data.search_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        queries=queries,
        authenticated_user_id=_authenticated_user_id(ctx),
    )


def merge_reference_pools(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    timeline_payload = dict(ctx.get("timeline_references") or {})
    search_payload = ctx.get("search_references") or {}
    timeline_rows = list(timeline_payload.get("timeline_reference_tweets") or [])
    search_rows = (
        list(search_payload.get("search_reference_tweets") or [])
        if isinstance(search_payload, dict)
        else []
    )
    merged = TickDataService.merge_reference_pool_rows(timeline_rows, search_rows)
    timeline_payload["timeline_reference_tweets"] = merged
    timeline_payload["search_merged_count"] = len(search_rows)
    timeline_payload["timeline_only_count"] = len(timeline_rows)
    if isinstance(search_payload, dict):
        sq = search_payload.get("search_queries")
        if isinstance(sq, list) and sq:
            timeline_payload["search_queries_run"] = sq
        search_errors = search_payload.get("reference_errors")
        if isinstance(search_errors, list) and search_errors:
            existing = list(timeline_payload.get("reference_errors") or [])
            timeline_payload["reference_errors"] = existing + search_errors
    ctx.set("timeline_references", timeline_payload)
    return StepResult(
        ok=True,
        payload={
            "merged_count": len(merged),
            "search_merged_count": len(search_rows),
        },
    )


def own_posts_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")
    return tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)

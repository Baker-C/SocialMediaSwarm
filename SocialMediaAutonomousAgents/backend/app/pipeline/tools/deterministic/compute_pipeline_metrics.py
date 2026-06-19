"""Compute engagement metrics per pipeline per account."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "deterministic.compute_pipeline_metrics"
TOOL_KIND = "deterministic"
TOOL_PURPOSE = "Compute engagement metrics per pipeline per account"
TOOL_READS = ["posts_by_pipeline"]
TOOL_WRITES = ["pipeline_metrics"]


def run(ctx: TickRunContext) -> StepResult:
    posts_by_pipeline: dict[str, dict[str, list[dict[str, Any]]]] = (
        ctx.get("posts_by_pipeline") or {}
    )
    result = compute(posts_by_pipeline=posts_by_pipeline)
    ctx.set("pipeline_metrics", result)
    return StepResult(ok=True, payload={"account_count": len(result)})


def compute(
    *,
    posts_by_pipeline: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {account_id: {pipeline_id: {post_count, avg_views, avg_likes, engagement_rate}}}."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for account_id, by_pipeline in posts_by_pipeline.items():
        account_metrics: dict[str, dict[str, Any]] = {}
        for pipeline_id, posts in by_pipeline.items():
            post_count = len(posts)
            total_views = sum(int(p.get("views") or 0) for p in posts)
            total_likes = sum(int(p.get("likes") or 0) for p in posts)
            avg_views = total_views / post_count if post_count else 0.0
            avg_likes = total_likes / post_count if post_count else 0.0
            engagement_rate = avg_likes / avg_views if avg_views > 0 else 0.0
            account_metrics[pipeline_id] = {
                "post_count": post_count,
                "avg_views": avg_views,
                "avg_likes": avg_likes,
                "engagement_rate": engagement_rate,
            }
        result[account_id] = account_metrics
    return result

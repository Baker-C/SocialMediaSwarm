"""Group recent posts by pipeline_id per account."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "deterministic.group_posts_by_pipeline"
TOOL_KIND = "deterministic"
TOOL_PURPOSE = "Group recent posts by pipeline_id per account"
TOOL_READS = ["recent_posts"]
TOOL_WRITES = ["posts_by_pipeline"]


def run(ctx: TickRunContext) -> StepResult:
    recent_posts: dict[str, list[dict[str, Any]]] = ctx.get("recent_posts") or {}
    result = group(recent_posts=recent_posts)
    ctx.set("posts_by_pipeline", result)
    return StepResult(ok=True, payload={"account_count": len(result)})


def group(
    *,
    recent_posts: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Return {account_id: {pipeline_id: [post, ...]}}."""
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for account_id, posts in recent_posts.items():
        by_pipeline: dict[str, list[dict[str, Any]]] = {}
        for post in posts:
            pipeline_id = str(post.get("pipeline_id") or "unknown")
            by_pipeline.setdefault(pipeline_id, []).append(post)
        result[account_id] = by_pipeline
    return result

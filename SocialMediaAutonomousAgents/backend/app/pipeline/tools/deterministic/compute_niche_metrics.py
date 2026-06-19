"""Pure-Python aggregation of engagement metrics grouped by niche per account."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "deterministic.compute_niche_metrics"
TOOL_KIND = "deterministic"
TOOL_PURPOSE = "Compute engagement metrics per niche per account"
TOOL_READS = (ArtifactKey.POSTS_WITH_NICHE,)
TOOL_WRITES = (ArtifactKey.NICHE_METRICS,)


def run(ctx: TickRunContext) -> StepResult:
    posts_with_niche: dict[str, list[dict[str, Any]]] = ctx.data.get("posts_with_niche") or {}
    niche_metrics = compute(posts_with_niche)
    ctx.set("niche_metrics", niche_metrics)
    return StepResult(ok=True, payload={"account_count": len(niche_metrics)})


def compute(
    posts_with_niche: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {account_id: {niche_id: {post_count, avg_views, avg_likes, engagement_rate}}}."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for account_id, posts in posts_with_niche.items():
        result[account_id] = _aggregate_niches(posts)
    return result


def _aggregate_niches(posts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        if not isinstance(post, dict):
            continue
        niche_id = post.get("niche_id") or "__unclassified__"
        buckets.setdefault(niche_id, []).append(post)

    out: dict[str, dict[str, Any]] = {}
    for niche_id, bucket in buckets.items():
        post_count = len(bucket)
        views = [_to_float(p.get("impression_count")) for p in bucket]
        likes = [_to_float(p.get("like_count")) for p in bucket]
        replies = [_to_float(p.get("reply_count")) for p in bucket]
        retweets = [_to_float(p.get("retweet_count")) for p in bucket]

        avg_views = _mean(views)
        avg_likes = _mean(likes)
        avg_replies = _mean(replies)
        avg_retweets = _mean(retweets)

        if avg_views and avg_views > 0:
            engagement_rate = (avg_likes + avg_replies + avg_retweets) / avg_views
        else:
            engagement_rate = 0.0

        out[niche_id] = {
            "post_count": post_count,
            "avg_views": avg_views,
            "avg_likes": avg_likes,
            "avg_replies": avg_replies,
            "avg_retweets": avg_retweets,
            "engagement_rate": engagement_rate,
        }
    return out


def _to_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mean(values: list[float]) -> float:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else 0.0

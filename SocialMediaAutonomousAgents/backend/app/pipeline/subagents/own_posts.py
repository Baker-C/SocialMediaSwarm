"""Own-post performance analysis (history → rank → pattern summary)."""

from __future__ import annotations

from typing import Any

from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

SUBAGENT_ID = "own_posts_reference_analyst"
SUBAGENT_PURPOSE = "Analyze top own posts for voice and success patterns"

MIN_POSTS = 3
MIN_TOP_N = 10


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank top own posts and produce a voice/success brief."""
    if deps.post_registry is None:
        brief = {"skipped": True, "skip_reason": "no_post_registry", "source": "own_posts"}
        ctx.set("own_posts_analysis", brief)
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry", payload=brief)

    if not ctx.get("own_posts"):
        pool_step = tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)
        if not pool_step.ok:
            return pool_step

    own_payload = ctx.get("own_posts") or {}
    rows = _rows_from_tracked(own_payload.get("posts") or [])
    if len(rows) < MIN_POSTS:
        brief = {
            "skipped": True,
            "skip_reason": "insufficient_own_posts",
            "source": "own_posts",
            "post_count": len(rows),
        }
        ctx.set("own_posts_analysis", brief)
        return StepResult(ok=True, skipped=True, skip_reason="insufficient_own_posts", payload=brief)

    rank = tool_catalog().deterministic.reference_rank.run(
        ctx,
        rows=rows,
        top_n=MIN_TOP_N,
        store_key="own_posts_ranked",
    )
    ranked = rank.payload.get("ranked") or []

    summary = tool_catalog().llm.reference_pattern_summary.run(
        ctx,
        source="own_posts",
        niche=ctx.niche,
        top_posts=ranked,
        features={"history_size": len(rows), "top_n": len(ranked)},
        store_key="own_posts_analysis",
    )

    brief = ctx.get("own_posts_analysis") or summary.payload
    ctx.set("own_posts_analysis", brief)
    return StepResult(ok=True, payload={"own_posts_analysis": brief})


def _rows_from_tracked(posts: list[Any]) -> list[dict[str, Any]]:
    """Normalize TrackedPost documents into reference-rank rows."""
    rows: list[dict[str, Any]] = []
    for doc in posts:
        if not isinstance(doc, dict):
            continue
        text = str(doc.get("post_text") or doc.get("text") or "").strip()
        raw = doc.get("raw_metrics") if isinstance(doc.get("raw_metrics"), dict) else {}
        row = {
            "tweet_id": doc.get("tweet_id"),
            "id": doc.get("tweet_id"),
            "text": text or str(raw.get("text") or ""),
            "like_count": doc.get("like_count") if doc.get("like_count") is not None else raw.get("like_count"),
            "reply_count": doc.get("reply_count") if doc.get("reply_count") is not None else raw.get("reply_count"),
            "retweet_count": doc.get("retweet_count") if doc.get("retweet_count") is not None else raw.get("retweet_count"),
            "impression_count": doc.get("impression_count")
            if doc.get("impression_count") is not None
            else raw.get("impression_count"),
            "posted_at": doc.get("posted_at"),
            "source": "own_posts",
        }
        if row.get("tweet_id"):
            rows.append(row)
    return rows

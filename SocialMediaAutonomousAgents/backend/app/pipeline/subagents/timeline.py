"""External timeline reference analysis (fetch → rank → pattern summary)."""

from __future__ import annotations

from typing import Any

from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls

SUBAGENT_ID = "timeline_reference_analyst"
SUBAGENT_PURPOSE = "Analyze top external timeline references for compose context"

MIN_TOP_N = 10


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank top timeline references and produce a pattern brief."""
    refs_payload = ctx.get("timeline_references")
    if not refs_payload:
        prof_step = _auth_user_id(ctx)
        fetch = tool_catalog().data.timeline_fetch.run(
            ctx,
            tick_data=deps.tick_data,
            authenticated_user_id=prof_step,
        )
        if not fetch.ok:
            return fetch
        refs_payload = ctx.get("timeline_references") or {}

    pool = TickDataService.merge_reference_pool(refs_payload)
    pool = filter_rows_with_urls(pool)
    if not pool:
        brief = {"skipped": True, "skip_reason": "no_reference_with_urls", "source": "timeline"}
        ctx.set("timeline_analysis", brief)
        return StepResult(ok=True, skipped=True, skip_reason="no_reference_with_urls", payload=brief)

    rank = tool_catalog().deterministic.reference_rank.run(
        ctx,
        rows=pool,
        top_n=MIN_TOP_N,
        store_key="timeline_ranked",
    )
    ranked = rank.payload.get("ranked") or []
    winner = rank.payload.get("winner")

    summary = tool_catalog().llm.reference_pattern_summary.run(
        ctx,
        source="timeline",
        niche=ctx.niche,
        top_posts=ranked,
        features={"pool_size": len(pool), "top_n": len(ranked)},
        store_key="timeline_analysis",
    )

    brief = ctx.get("timeline_analysis") or summary.payload
    if isinstance(brief, dict) and winner:
        brief["selected_winner_id"] = winner.get("tweet_id")
    ctx.set("timeline_analysis", brief)
    return StepResult(ok=True, payload={"timeline_analysis": brief, "winner": winner})


def _auth_user_id(ctx: TickRunContext) -> str | None:
    bundle: Any = ctx.get("account_bundle") or {}
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    if isinstance(prof, dict) and prof.get("id") is not None:
        return str(prof["id"])
    return None

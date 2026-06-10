"""Thin step wrappers — hide tool argument wiring from the runbook."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.services.reference_analysis import (
    authenticated_user_id_from_bundle,
    avg_char_count,
    enrich_row_features,
    rows_from_tracked,
    top_entities,
)
from app.pipeline.types.artifacts import (
    ArtifactKey,
    ReferencePatternBrief,
    TimelineReferencesPayload,
)
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls

MIN_TOP_N = 10
MIN_OWN_POSTS = 3


def load_account_bundle(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    return tool_catalog().data.account_profile.run(ctx, tick_data=deps.tick_data)


def fetch_timeline_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    bundle_raw = ctx.get(ArtifactKey.ACCOUNT_BUNDLE.value) or {}
    auth_id = authenticated_user_id_from_bundle(bundle_raw if isinstance(bundle_raw, dict) else {})
    return tool_catalog().data.timeline_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        authenticated_user_id=auth_id,
    )


def fetch_search_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if not settings.trend_tweet_search_enabled:
        return StepResult(ok=True, skipped=True, skip_reason="search_disabled")
    acc = deps.repo.load(ctx.account_id)
    if acc is None:
        return StepResult(ok=False, skip_reason="account_not_found")
    queries = list(acc.search_queries or [])
    if not queries:
        return StepResult(ok=True, skipped=True, skip_reason="no_search_queries")
    bundle_raw = ctx.get(ArtifactKey.ACCOUNT_BUNDLE.value) or {}
    auth_id = authenticated_user_id_from_bundle(bundle_raw if isinstance(bundle_raw, dict) else {})
    return tool_catalog().data.search_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        queries=queries,
        authenticated_user_id=auth_id,
    )


def merge_external_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    timeline_raw = ctx.get(ArtifactKey.TIMELINE_REFERENCES.value) or {}
    search_raw = ctx.get(ArtifactKey.SEARCH_REFERENCES.value) or {}
    timeline_payload = dict(timeline_raw) if isinstance(timeline_raw, dict) else {}
    search_payload = search_raw if isinstance(search_raw, dict) else {}
    timeline_rows = list(timeline_payload.get("timeline_reference_tweets") or [])
    search_rows = list(search_payload.get("search_reference_tweets") or [])
    merged = TickDataService.merge_reference_pool_rows(timeline_rows, search_rows)
    timeline_payload["timeline_reference_tweets"] = merged
    timeline_payload["search_merged_count"] = len(search_rows)
    timeline_payload["timeline_only_count"] = len(timeline_rows)
    if search_payload:
        sq = search_payload.get("search_queries")
        if isinstance(sq, list) and sq:
            timeline_payload["search_queries_run"] = sq
        search_errors = search_payload.get("reference_errors")
        if isinstance(search_errors, list) and search_errors:
            existing = list(timeline_payload.get("reference_errors") or [])
            timeline_payload["reference_errors"] = existing + search_errors
    ctx.set_artifact(ArtifactKey.TIMELINE_REFERENCES, timeline_payload)
    return StepResult(
        ok=True,
        payload={
            "merged_count": len(merged),
            "search_merged_count": len(search_rows),
        },
    )


def fetch_own_post_history(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")
    return tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)


def rank_external_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    refs_raw = ctx.get(ArtifactKey.TIMELINE_REFERENCES.value) or {}
    refs_payload = refs_raw if isinstance(refs_raw, dict) else {}
    pool = TickDataService.merge_reference_pool(refs_payload)
    pool = filter_rows_with_urls(pool)
    if not pool:
        ctx.set_artifact(
            ArtifactKey.TIMELINE_RANKED,
            {"ranked": [], "winner": None},
        )
        return StepResult(ok=True, skipped=True, skip_reason="no_reference_with_urls")
    return tool_catalog().deterministic.reference_rank.run(
        ctx,
        rows=pool,
        top_n=MIN_TOP_N,
        store_key=ArtifactKey.TIMELINE_RANKED.value,
    )


def brief_external_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    ranked_raw = ctx.get(ArtifactKey.TIMELINE_RANKED.value) or {}
    ranked_payload = ranked_raw if isinstance(ranked_raw, dict) else {}
    ranked = list(ranked_payload.get("ranked") or [])
    winner = ranked_payload.get("winner")

    if not ranked:
        brief = ReferencePatternBrief(
            skipped=True,
            skip_reason="no_reference_with_urls",
            source="timeline",
        )
        ctx.set_artifact(ArtifactKey.TIMELINE_ANALYSIS, brief.model_dump())
        return StepResult(ok=True, skipped=True, skip_reason="no_reference_with_urls", payload=brief.model_dump())

    enriched = [enrich_row_features(r) for r in ranked if isinstance(r, dict)]
    summary = tool_catalog().llm.reference_pattern_summary.run(
        ctx,
        source="timeline",
        niche=ctx.niche,
        top_posts=enriched,
        features={
            "pool_size": len(enriched),
            "top_n": len(enriched),
            "entity_tags": top_entities(enriched),
            "avg_char_count": avg_char_count(enriched),
        },
        store_key=ArtifactKey.TIMELINE_ANALYSIS.value,
    )

    brief_raw = ctx.get(ArtifactKey.TIMELINE_ANALYSIS.value) or summary.payload
    brief_dict = dict(brief_raw) if isinstance(brief_raw, dict) else {}
    if winner and isinstance(winner, dict):
        brief_dict["selected_winner_id"] = winner.get("tweet_id")
        ctx.set_artifact(ArtifactKey.TIMELINE_ANALYSIS, brief_dict)
    return StepResult(ok=True, payload={"timeline_analysis": brief_dict, "winner": winner})


def rank_own_posts(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        ctx.set_artifact(
            ArtifactKey.OWN_POSTS_RANKED,
            {"ranked": [], "winner": None},
        )
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")

    own_raw = ctx.get(ArtifactKey.OWN_POSTS.value)
    if not own_raw:
        pool_step = tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)
        if not pool_step.ok:
            return pool_step
        own_raw = ctx.get(ArtifactKey.OWN_POSTS.value) or {}

    own_payload = own_raw if isinstance(own_raw, dict) else {}
    rows = rows_from_tracked(own_payload.get("posts") or [])
    if len(rows) < MIN_OWN_POSTS:
        ctx.set_artifact(
            ArtifactKey.OWN_POSTS_RANKED,
            {"ranked": [], "winner": None},
        )
        return StepResult(
            ok=True,
            skipped=True,
            skip_reason="insufficient_own_posts",
            payload={"post_count": len(rows)},
        )

    return tool_catalog().deterministic.reference_rank.run(
        ctx,
        rows=rows,
        top_n=MIN_TOP_N,
        store_key=ArtifactKey.OWN_POSTS_RANKED.value,
    )


def brief_own_posts(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    if deps.post_registry is None:
        brief = ReferencePatternBrief(
            skipped=True,
            skip_reason="no_post_registry",
            source="own_posts",
        )
        ctx.set_artifact(ArtifactKey.OWN_POSTS_ANALYSIS, brief.model_dump())
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry", payload=brief.model_dump())

    ranked_raw = ctx.get(ArtifactKey.OWN_POSTS_RANKED.value) or {}
    ranked_payload = ranked_raw if isinstance(ranked_raw, dict) else {}
    ranked = list(ranked_payload.get("ranked") or [])

    own_raw = ctx.get(ArtifactKey.OWN_POSTS.value) or {}
    own_payload = own_raw if isinstance(own_raw, dict) else {}
    history_rows = rows_from_tracked(own_payload.get("posts") or [])

    if len(history_rows) < MIN_OWN_POSTS or not ranked:
        brief = ReferencePatternBrief(
            skipped=True,
            skip_reason="insufficient_own_posts",
            source="own_posts",
            post_count=len(history_rows),
        )
        ctx.set_artifact(ArtifactKey.OWN_POSTS_ANALYSIS, brief.model_dump())
        return StepResult(ok=True, skipped=True, skip_reason="insufficient_own_posts", payload=brief.model_dump())

    enriched = [enrich_row_features(r) for r in ranked if isinstance(r, dict)]
    summary = tool_catalog().llm.reference_pattern_summary.run(
        ctx,
        source="own_posts",
        niche=ctx.niche,
        top_posts=enriched,
        features={
            "history_size": len(history_rows),
            "top_n": len(enriched),
            "entity_tags": top_entities(enriched),
            "avg_char_count": avg_char_count(enriched),
        },
        store_key=ArtifactKey.OWN_POSTS_ANALYSIS.value,
    )
    brief_raw = ctx.get(ArtifactKey.OWN_POSTS_ANALYSIS.value) or summary.payload
    return StepResult(ok=True, payload={"own_posts_analysis": brief_raw})


# Backward-compatible aliases for tests and callers migrating gradually
profile = load_account_bundle
timeline_pool = fetch_timeline_references
search_pool = fetch_search_references
merge_reference_pools = merge_external_references
own_posts_pool = fetch_own_post_history

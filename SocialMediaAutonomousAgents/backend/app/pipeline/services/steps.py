"""Thin step wrappers — hide tool argument wiring from the runbook."""

from __future__ import annotations

from typing import Any

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.tools.data import (
    account_profile,
    own_posts_fetch,
    search_fetch,
)
from app.pipeline.tools.deterministic import reference_rank
from app.pipeline.tools.llm import reference_pattern_summary
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
)
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls
from app.social.trend_query import trend_topic_query

MIN_TOP_N = 10
MIN_OWN_POSTS = 3
# Per-niche cap for the recent-search reference fetch (X API max is 100).
SEARCH_RESULTS_PER_NICHE = 50


def load_account_bundle(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    return account_profile.run(ctx, tick_data=deps.tick_data)


def _trend_search_queries(twitter: Any, account_id: str, *, limit: int = 8) -> list[str]:
    """Keyword queries from the account's live (personalized) X trends."""
    try:
        trends = twitter.get_trends(account_id, limit=20)
    except Exception:
        return []
    out: list[str] = []
    for item in (trends or {}).get("trends") or []:
        name = item.get("name") if isinstance(item, dict) else None
        if not name:
            continue
        q = trend_topic_query(str(name))
        if q and q not in out:
            out.append(q)
        if len(out) >= limit:
            break
    return out


def fetch_search_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    acc = deps.repo.load(ctx.account_id)
    if acc is None:
        return StepResult(ok=False, skip_reason="account_not_found")
    # Query source, in priority order:
    #   1. Scored niches  — specific topics the account is observed to ride.
    #   2. Live X trends  — the hot topics to ride right now (keyword-extracted).
    #   3. Category       — the account's descriptor; last-resort so search never
    #                       runs dry even with no niches and no trends.
    queries = [n.niche.strip() for n in acc.niches if n.niche and n.niche.strip()]
    if not queries:
        queries = _trend_search_queries(deps.twitter, ctx.account_id)
    if not queries:
        category = (acc.category or "").strip()
        if category:
            queries = [category]
    if not queries:
        return StepResult(ok=True, skipped=True, skip_reason="no_search_topics")
    bundle_raw = ctx.get(ArtifactKey.ACCOUNT_BUNDLE.value) or {}
    auth_id = authenticated_user_id_from_bundle(bundle_raw if isinstance(bundle_raw, dict) else {})
    return search_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        queries=queries,
        authenticated_user_id=auth_id,
        max_results_per_query=SEARCH_RESULTS_PER_NICHE,
    )


def collect_external_references(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Promote the per-niche search results into the external reference pool.

    The pool is stored under TIMELINE_REFERENCES (the key downstream rank/brief
    steps read); the following-timeline pull was removed, so search is the sole
    external source.
    """
    _ = deps
    search_raw = ctx.get(ArtifactKey.SEARCH_REFERENCES.value) or {}
    search_payload = search_raw if isinstance(search_raw, dict) else {}
    search_rows = list(search_payload.get("search_reference_tweets") or [])

    pool: dict = {
        "timeline_reference_tweets": search_rows,
        "search_merged_count": len(search_rows),
    }
    sq = search_payload.get("search_queries")
    if isinstance(sq, list) and sq:
        pool["search_queries_run"] = sq
    search_errors = search_payload.get("reference_errors")
    if isinstance(search_errors, list) and search_errors:
        pool["reference_errors"] = list(search_errors)

    ctx.set_artifact(ArtifactKey.TIMELINE_REFERENCES, pool)
    return StepResult(ok=True, payload={"reference_count": len(search_rows)})


def fetch_own_post_history(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")
    return own_posts_fetch.run(ctx, post_registry=deps.post_registry)


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
    return reference_rank.run(
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
    summary = reference_pattern_summary.run(
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
        pool_step = own_posts_fetch.run(ctx, post_registry=deps.post_registry)
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

    return reference_rank.run(
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
    summary = reference_pattern_summary.run(
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

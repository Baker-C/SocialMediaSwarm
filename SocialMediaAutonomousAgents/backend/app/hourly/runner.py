"""Hourly tick entry: pre → crew → post."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.hourly.compose_timeline_post import compose_formatted_post
from app.hourly.context import TickContext
from app.hourly.orchestration.post_tick import finalize_post, phase3_global_persist, phase4_backup_noop
from app.hourly.orchestration.pre_tick import phase1_global_setup, should_skip_account
from app.hourly.orchestration.post_guard import release_post_guard, try_begin_post
from app.hourly.orchestration.slot_claim import (
    release_hourly_slot_reservation,
    reload_account,
    try_reserve_hourly_slot,
)
from app.hourly.pipeline_trace import trace_step
from app.hourly.schemas import TickInput, TickMode
from app.hourly.tweet_topic_preanalysis import (
    apply_preanalysis_to_account_bundle,
    run_reference_preanalysis,
    select_top_timeline_reference,
)
from app.hourly_crew.tools import tick_data as tick_data_tools
from app.models.tracked_post import PostCreationMetrics
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository, current_post_slot_key
from app.social.tweet_enrichment import filter_rows_with_urls

logger = logging.getLogger(__name__)

__all__ = [
    "TickContext",
    "TickMode",
    "build_tick_context",
    "current_post_slot_key",
    "run_account_pipeline",
    "run_hourly_tick",
]


def build_tick_context(
    *,
    repo: AccountRepository,
    twitter: Any,
    creator: Any,
    guardian: Any,
    tick_data: Any,
    post_registry: Any,
    mode: TickMode = "scheduled",
    force_account_ids: frozenset[str] | None = None,
    max_candidates: int = 5,
    max_regeneration_rounds: int = 3,
    bypass_post_cooldown: bool = False,
) -> TickContext:
    slot = current_post_slot_key()
    now_iso = datetime.now(timezone.utc).isoformat()
    ctx = TickContext(
        repo=repo,
        twitter=twitter,
        creator=creator,
        guardian=guardian,
        tick_data=tick_data,
        post_registry=post_registry,
        slot=slot,
        now_iso=now_iso,
        mode=mode,
        force_account_ids=force_account_ids,
        max_candidates=max_candidates,
        max_regeneration_rounds=max_regeneration_rounds,
        bypass_post_cooldown=bypass_post_cooldown,
        accounts=[],
    )
    trace_step(
        "_global",
        "build_tick_context",
        {
            "slot": slot,
            "mode": mode,
            "force_account_ids": list(force_account_ids) if force_account_ids else None,
            "max_candidates": max_candidates,
            "max_regeneration_rounds": max_regeneration_rounds,
        },
        handoff_to="phase1_global_setup",
    )
    return ctx


def run_account_pipeline(ctx: TickContext, account: AccountDocument) -> dict[str, Any]:
    aid = account.account_id
    trace_step(
        aid,
        "pre_tick_input",
        {"account_id": aid, "niche": account.niche, "slot": ctx.slot, "mode": ctx.mode},
        handoff_to="reload_account",
    )

    fresh = reload_account(ctx, aid)
    if fresh is None:
        out = {"account_id": aid, "skipped": "account_not_found"}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out
    account = fresh

    skip = should_skip_account(ctx, account)
    if skip:
        out = {"account_id": aid, "skipped": skip}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    if ctx.mode == "scheduled" and account.last_post_slot == ctx.slot:
        out = {"account_id": aid, "skipped": "already_posted_this_hour"}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    _, guard_skip = try_begin_post(ctx, aid, account)
    if guard_skip:
        out = {"account_id": aid, "skipped": guard_skip}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    reservation, reserve_skip = try_reserve_hourly_slot(ctx, aid)
    if reserve_skip:
        release_post_guard(ctx, aid)
        out = {"account_id": aid, "skipped": reserve_skip}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out
    assert reservation is not None
    account = reservation.account

    trace_step(
        aid,
        "slot_reserved",
        {"slot": ctx.slot, "previous_slot": reservation.previous_slot},
        handoff_to="2a_compile_account_bundle",
    )

    bundle_account = tick_data_tools.compile_account_bundle(ctx.tick_data, account.account_id)
    trace_step(aid, "2a_account_bundle", bundle_account, handoff_to="2a_timeline_references")

    prof = bundle_account.get("profile") or {}
    fc = prof.get("followers_count")
    if isinstance(fc, int):
        account.followers = fc

    auth_user_id: str | None = None
    prof = bundle_account.get("profile")
    if isinstance(prof, dict) and prof.get("id") is not None:
        auth_user_id = str(prof["id"])

    refs_payload = tick_data_tools.compile_timeline_reference_tweets(
        ctx.tick_data,
        account.account_id,
        authenticated_user_id=auth_user_id,
        slot=ctx.slot,
    )
    bundle_account["timeline_reference_tweets"] = refs_payload.get("timeline_reference_tweets") or []
    bundle_account["reference_errors"] = refs_payload.get("reference_errors") or []
    trace_step(aid, "2a_timeline_references", refs_payload, handoff_to="2a_reference_pool")

    reference_pool = tick_data_tools.merge_reference_pool(refs_payload)
    reference_pool = filter_rows_with_urls(reference_pool)
    trace_step(
        aid,
        "2a_reference_pool_urls_only",
        {"count": len(reference_pool)},
        handoff_to="2a_half_reference_preanalysis",
    )

    topic_preanalysis = run_reference_preanalysis(reference_pool, niche=account.niche)
    trace_step(aid, "2a_half_reference_preanalysis", topic_preanalysis.model_dump(), handoff_to="apply_preanalysis")

    if topic_preanalysis.skipped:
        release_hourly_slot_reservation(ctx, aid)
        release_post_guard(ctx, aid)
        out = {"account_id": aid, "skipped": topic_preanalysis.skip_reason or "no_reference_with_urls"}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    bundle_account = apply_preanalysis_to_account_bundle(bundle_account, topic_preanalysis)
    trace_step(aid, "2a_filtered_bundle", bundle_account, handoff_to="compose_post")

    winner = select_top_timeline_reference(reference_pool)
    if winner is None:
        release_hourly_slot_reservation(ctx, aid)
        release_post_guard(ctx, aid)
        out = {"account_id": aid, "skipped": "no_reference_with_urls"}
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    tick_input = TickInput(
        account_id=account.account_id,
        niche=account.niche,
        slot=ctx.slot,
        mode=ctx.mode,
        account_system_prompt=(account.system_prompt or "").strip(),
        max_candidates=ctx.max_candidates,
    )
    trace_step(aid, "tick_input", tick_input, handoff_to="compose_and_safety")

    last_reject: str | None = None
    selected_body: str | None = None
    selected_round: int | None = None

    for reg_round in range(ctx.max_regeneration_rounds):
        body = compose_formatted_post(winner, account.niche, regeneration_round=reg_round)
        trace_step(
            aid,
            f"compose_round_{reg_round}",
            {"body": body, "chosen_embed_url": topic_preanalysis.chosen_embed_url},
            handoff_to="safety_filter",
        )
        approved, reject = ctx.guardian.evaluate(body)
        trace_step(
            aid,
            f"safety_round_{reg_round}",
            {"approved": approved, "reject": reject, "body": body},
            handoff_to="post_tick" if approved else f"regenerate_round_{reg_round + 1}",
        )
        if approved:
            selected_body = body
            selected_round = reg_round
            break
        last_reject = reject or "safety_rejected"

    if selected_body is None:
        release_hourly_slot_reservation(ctx, aid)
        release_post_guard(ctx, aid)
        out = {"account_id": account.account_id, "rejected": last_reject or "all_compose_attempts_failed"}
        trace_step(aid, "pipeline_rejected", out, handoff_to="(end)")
        return out

    trace_step(
        aid,
        "post_tick_input",
        {
            "polished_body": selected_body,
            "regeneration_round": selected_round,
            "chosen_embed_url": topic_preanalysis.chosen_embed_url,
            "source_reference_tweet_id": topic_preanalysis.selected_tweet_ids[0]
            if topic_preanalysis.selected_tweet_ids
            else None,
        },
        handoff_to="finalize_post",
    )

    pull_stats = refs_payload.get("pulled_tweet_stats") if isinstance(refs_payload.get("pulled_tweet_stats"), dict) else {}
    source_id = topic_preanalysis.selected_tweet_ids[0] if topic_preanalysis.selected_tweet_ids else None
    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        tweets_pulled=len(reference_pool),
        tweets_pulled_new=int(pull_stats.get("new_count") or 0),
        tweets_pulled_duplicates=int(pull_stats.get("duplicate_count") or 0),
        regeneration_round=selected_round if selected_round is not None else 0,
        source_reference_tweet_id=source_id,
        chosen_embed_url=topic_preanalysis.chosen_embed_url,
    )
    result = finalize_post(
        ctx,
        account,
        selected_body,
        regeneration_round=selected_round,
        earlier_reject=last_reject,
        creation_metrics=creation_metrics,
    )
    trace_step(aid, "post_tick_result", result, handoff_to="(end)")
    return result


def run_hourly_tick(ctx: TickContext) -> dict[str, Any]:
    phase1_global_setup(ctx)
    trace_step(
        "_global",
        "phase1_accounts_loaded",
        {
            "slot": ctx.slot,
            "account_ids": [a.account_id for a in ctx.accounts],
            "count": len(ctx.accounts),
        },
        handoff_to="run_account_pipeline (per account)",
    )
    results: list[dict[str, Any]] = []
    for account in ctx.accounts:
        results.append(run_account_pipeline(ctx, account))
    phase3_global_persist(ctx)
    phase4_backup_noop()
    out = {"slot": ctx.slot, "results": results}
    trace_step("_global", "tick_complete", out, handoff_to="(end)")
    return out

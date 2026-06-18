"""Interval tick entry: pre → compose → post."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.interval.compose_timeline_post import compose_formatted_post
from app.interval.context import TickContext
from app.interval.orchestration.post_tick import finalize_post, phase3_global_persist, phase4_backup_noop
from app.interval.orchestration.pre_tick import phase1_global_setup, should_skip_account
from app.interval.orchestration.post_guard import release_post_pipeline_guards, try_begin_post
from app.interval.orchestration.slot_claim import (
    reload_account,
    try_reserve_interval_slot,
)
from app.interval.pipeline_trace import trace_step
from app.interval.schemas import TickInput, TickMode
from app.agents.safety_guardian import is_niche_mismatch_reject
from app.interval.reference_context import format_reference_context_for_compose
from app.interval.reference_phase import run_reference_phase
from app.interval.tweet_topic_preanalysis import (
    GatheredTweet,
    apply_preanalysis_to_account_bundle,
    preanalysis_from_winner,
)
from app.services.copied_references import copied_reference_exclude_set, record_copied_reference
from app.models.tracked_post import PostCreationMetrics
from app.models.account import AccountDocument
from app.core.config import settings
from app.services.account_repository import AccountRepository, current_interval_slot_key
from app.services.pipeline_progress import progress_active, progress_done, progress_error
from app.pipeline.events.dispatcher import (
    emit_run_completed,
    emit_run_started,
    emit_step_completed,
    emit_step_failed,
    emit_step_started,
    run_events,
)
from app.pipeline.events.sinks import NatsPublishSink
from app.metrics.derived import extract_entities, extract_text_features
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)

__all__ = [
    "TickContext",
    "TickMode",
    "build_tick_context",
    "current_interval_slot_key",
    "run_account_pipeline",
    "run_interval_tick",
]


def build_tick_context(
    *,
    repo: AccountRepository,
    twitter: Any,
    guardian: Any,
    tick_data: Any,
    post_registry: Any,
    mode: TickMode = "scheduled",
    force_account_ids: frozenset[str] | None = None,
    max_candidates: int = 5,
    max_regeneration_rounds: int | None = None,
    bypass_post_cooldown: bool = False,
    forced_run_id: str | None = None,
) -> TickContext:
    slot = current_interval_slot_key()
    now_iso = datetime.now(timezone.utc).isoformat()
    regen_rounds = (
        max_regeneration_rounds
        if max_regeneration_rounds is not None
        else max(1, int(settings.max_regeneration_rounds))
    )
    ctx = TickContext(
        repo=repo,
        twitter=twitter,
        guardian=guardian,
        tick_data=tick_data,
        post_registry=post_registry,
        slot=slot,
        now_iso=now_iso,
        mode=mode,
        force_account_ids=force_account_ids,
        max_candidates=max_candidates,
        max_regeneration_rounds=regen_rounds,
        bypass_post_cooldown=bypass_post_cooldown,
        forced_run_id=forced_run_id,
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
            "max_regeneration_rounds": regen_rounds,
        },
        handoff_to="phase1_global_setup",
    )
    return ctx


def _orch_active(step_id: str, label: str | None = None) -> None:
    progress_active(step_id, label)
    emit_step_started(step_id, scope="orchestrator", purpose=label)


def _orch_done(step_id: str, label: str | None = None) -> None:
    progress_done(step_id, label)
    emit_step_completed(step_id, scope="orchestrator", purpose=label)


def _orch_error(step_id: str, message: str) -> None:
    progress_error(step_id, message)
    emit_step_failed(
        step_id, scope="orchestrator", error={"type": "orchestrator", "message": message}
    )


def _run_status_from_out(out: dict[str, Any]) -> str:
    if out.get("skipped"):
        return "skipped"
    if out.get("rejected"):
        return "rejected"
    if out.get("error"):
        return "error"
    return "ok"


def run_account_pipeline(ctx: TickContext, account: AccountDocument) -> dict[str, Any]:
    """Public entry: wraps the per-account pipeline in an event-sourced run."""
    run_id = ctx.forced_run_id or uuid4().hex
    started = time.monotonic()
    with run_events(
        run_id=run_id,
        account_id=account.account_id,
        slot=ctx.slot,
        mode=ctx.mode,
        sinks=[NatsPublishSink()],
    ):
        emit_run_started(niche=account.category or "")
        status = "error"
        try:
            out = _run_account_pipeline(ctx, account)
            status = _run_status_from_out(out)
            return out
        finally:
            emit_run_completed(
                status=status, duration_ms=int((time.monotonic() - started) * 1000)
            )


def _run_account_pipeline(ctx: TickContext, account: AccountDocument) -> dict[str, Any]:
    followers_at_post: int | None = None
    aid = account.account_id
    outcomes = PipelineOutcomeRepository()
    trace_step(
        aid,
        "pre_tick_input",
        {"account_id": aid, "niche": account.category, "slot": ctx.slot, "mode": ctx.mode},
        handoff_to="reload_account",
    )

    _orch_active("load_account")
    fresh = reload_account(ctx, aid)
    if fresh is None:
        _orch_error("load_account", "account_not_found")
        out = {"account_id": aid, "skipped": "account_not_found"}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason="account_not_found")
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out
    account = fresh

    skip = should_skip_account(ctx, account)
    if skip:
        _orch_error("load_account", skip)
        out = {"account_id": aid, "skipped": skip}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason=skip)
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    if ctx.mode == "scheduled" and account.last_interval_slot == ctx.slot:
        _orch_error("load_account", "already_posted_this_interval")
        out = {"account_id": aid, "skipped": "already_posted_this_interval"}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason="already_posted_this_interval")
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out
    _orch_done("load_account")

    _orch_active("post_lock")
    _, guard_skip = try_begin_post(ctx, aid, account)
    if guard_skip:
        _orch_error("post_lock", guard_skip)
        out = {"account_id": aid, "skipped": guard_skip}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason=guard_skip)
        trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
        return out

    try:
        reservation, reserve_skip = try_reserve_interval_slot(ctx, aid)
        if reserve_skip:
            _orch_error("post_lock", reserve_skip)
            out = {"account_id": aid, "skipped": reserve_skip}
            outcomes.append(account_id=aid, phase="runner", status="skipped", reason=reserve_skip)
            trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
            return out
        assert reservation is not None
        account = reservation.account
        _orch_done("post_lock")

        trace_step(
            aid,
            "slot_reserved",
            {"slot": ctx.slot, "previous_slot": reservation.previous_slot},
            handoff_to="run_reference_phase",
        )

        copied_exclude = copied_reference_exclude_set(account)
        ref = run_reference_phase(ctx, account, copied_exclude=copied_exclude)
        if not ref.ok:
            out = {"account_id": aid, "skipped": ref.skip_reason or "reference_phase_failed"}
            outcomes.append(
                account_id=aid,
                phase="runner",
                status="skipped",
                reason=ref.skip_reason or "reference_phase_failed",
            )
            trace_step(aid, "pre_tick_skip", out, handoff_to="(end)")
            return out

        bundle_account = ref.bundle_account
        refs_payload = ref.refs_payload
        reference_pool = ref.reference_pool
        ranked_refs = ref.ranked_refs
        reference_context_block = format_reference_context_for_compose(
            ref.timeline_analysis,
            ref.own_posts_analysis,
        )

        prof = bundle_account.get("profile") or {}
        fc = prof.get("followers_count")
        if isinstance(fc, int):
            account.followers = fc
            followers_at_post = fc

        trace_step(aid, "2a_account_bundle", bundle_account, handoff_to="2a_timeline_references")
        trace_step(aid, "2a_timeline_references", refs_payload, handoff_to="2a_reference_pool")
        trace_step(
            aid,
            "2a_reference_pool_urls_only",
            {"count": len(reference_pool)},
            handoff_to="timeline_analysis",
        )
        trace_step(
            aid,
            "timeline_analysis",
            ref.timeline_analysis,
            handoff_to="own_posts_analysis",
        )
        trace_step(
            aid,
            "own_posts_analysis",
            ref.own_posts_analysis,
            handoff_to="2a_reference_ranked",
        )
        trace_step(
            aid,
            "2a_reference_ranked",
            {
                "count": len(ranked_refs),
                "top_ids": [t.tweet_id for t in ranked_refs[:5]],
                "copied_reference_count": len(copied_exclude),
            },
            handoff_to="compose_post",
        )

        tick_input = TickInput(
            account_id=account.account_id,
            niche=account.category,
            slot=ctx.slot,
            mode=ctx.mode,
            account_personality=(account.personality or "").strip(),
            max_candidates=ctx.max_candidates,
        )
        trace_step(aid, "tick_input", tick_input, handoff_to="compose_and_safety")

        last_reject: str | None = None
        selected_body: str | None = None
        selected_round: int | None = None
        winner: GatheredTweet | None = None
        topic_preanalysis = None
        references_tried = 0
        _orch_active("compose")

        for ref_idx, candidate in enumerate(ranked_refs):
            winner = candidate
            topic_preanalysis = preanalysis_from_winner(winner)
            references_tried += 1
            bundle_account = apply_preanalysis_to_account_bundle(bundle_account, topic_preanalysis)
            trace_step(
                aid,
                f"reference_attempt_{ref_idx}",
                {
                    "tweet_id": winner.tweet_id,
                    "popularity_score": winner.popularity_score,
                    "chosen_embed_url": topic_preanalysis.chosen_embed_url,
                },
                handoff_to="compose_and_safety",
            )

            candidate_reject: str | None = None
            for reg_round in range(ctx.max_regeneration_rounds):
                body = compose_formatted_post(
                    winner,
                    account.category,
                    account_posting_prompt=(account.posting_prompt or "").strip(),
                    account_personality=(account.personality or "").strip(),
                    contrast_patterns=list(account.contrast_patterns or []),
                    punctuation_rules=list(account.punctuation_rules or []),
                    reference_context_block=reference_context_block,
                    regeneration_round=reg_round,
                    safety_reject_reason=candidate_reject if reg_round > 0 else None,
                )
                trace_step(
                    aid,
                    f"compose_r{ref_idx}_round_{reg_round}",
                    {"body": body, "chosen_embed_url": topic_preanalysis.chosen_embed_url},
                    handoff_to="safety_filter",
                )
                _orch_active("safety")
                approved, reject = ctx.guardian.evaluate(body, niche=account.category)
                trace_step(
                    aid,
                    f"safety_r{ref_idx}_round_{reg_round}",
                    {"approved": approved, "reject": reject, "body": body},
                    handoff_to="post_tick" if approved else f"regenerate_round_{reg_round + 1}",
                )
                if approved:
                    _orch_done("safety")
                    selected_body = body
                    selected_round = reg_round
                    break
                _orch_done("safety")
                candidate_reject = reject or "safety_rejected"
                if is_niche_mismatch_reject(candidate_reject):
                    logger.info(
                        "reference_attempt niche_mismatch account=%s tweet_id=%s — trying next source",
                        aid,
                        winner.tweet_id,
                    )
                    last_reject = candidate_reject
                    break

            if selected_body is not None:
                break
            last_reject = candidate_reject or last_reject

        if selected_body is None or winner is None or topic_preanalysis is None:
            _orch_error("compose", last_reject or "all_compose_attempts_failed")
            out = {
                "account_id": account.account_id,
                "rejected": last_reject or "all_compose_attempts_failed",
                "references_tried": references_tried,
            }
            outcomes.append(
                account_id=aid,
                phase="runner",
                status="rejected",
                reason=last_reject or "all_compose_attempts_failed",
                details={"references_tried": references_tried},
            )
            trace_step(aid, "pipeline_rejected", out, handoff_to="(end)")
            return out
        _orch_done("compose")

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
        source_metrics_at_pick = None
        if winner is not None:
            source_metrics_at_pick = {
                "tweet_id": winner.tweet_id,
                "popularity_score": winner.popularity_score,
                "author_followers_count": winner.metrics.get("author_followers_count"),
                "quote_count": winner.metrics.get("quote_count"),
                "impression_count": winner.metrics.get("impression_count"),
                "text_features": extract_text_features(winner.text),
                "entity_tags": extract_entities(winner.metrics),
            }
        creation_metrics = PostCreationMetrics(
            candidates_created=1,
            tweets_pulled=len(reference_pool),
            tweets_pulled_new=int(pull_stats.get("new_count") or 0),
            tweets_pulled_duplicates=int(pull_stats.get("duplicate_count") or 0),
            regeneration_round=selected_round if selected_round is not None else 0,
            source_reference_tweet_id=source_id,
            chosen_embed_url=topic_preanalysis.chosen_embed_url,
            voice_version_hash=account.voice_version_hash,
            voice_version_seq=account.voice_version_seq,
            voice_version_label=account.voice_version_label,
            source_reference_metrics_at_pick=source_metrics_at_pick,
        )
        _orch_active("publish")
        result = finalize_post(
            ctx,
            account,
            selected_body,
            regeneration_round=selected_round,
            earlier_reject=last_reject,
            creation_metrics=creation_metrics,
            source_reference_tweet_id=source_id,
            followers_at_post=followers_at_post,
        )
        _orch_done("publish")
        _orch_active("complete")
        _orch_done("complete")
        trace_step(aid, "post_tick_result", result, handoff_to="(end)")
        outcomes.append(account_id=aid, phase="runner", status="ok")
        return result
    finally:
        release_post_pipeline_guards(ctx, aid)


def run_interval_tick(ctx: TickContext) -> dict[str, Any]:
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

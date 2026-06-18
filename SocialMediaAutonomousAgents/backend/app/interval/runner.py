"""Interval tick entry: pre → compose → post."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.cost_meter import CostMeter
from app.core.config import settings
from app.infrastructure.claude_client import drain_run_llm_cost_usd
from app.interval.context import TickContext
from app.interval.orchestration.post_guard import release_post_pipeline_guards, try_begin_post
from app.interval.orchestration.slot_claim import (
    reload_account,
    try_reserve_interval_slot,
)
from app.interval.orchestration.pre_tick import phase1_global_setup, should_skip_account
from app.interval.orchestration.post_tick import finalize_post, phase3_global_persist, phase4_backup_noop
from app.interval.pipeline_trace import trace_step
from app.interval.run_deps import post_run_deps_from_tick
from app.interval.schemas import TickInput, TickMode
from app.models.account import AccountDocument
from app.models.tracked_post import PostCreationMetrics
from app.pipeline._runbook_engine import run_steps
from app.pipeline.events.dispatcher import (
    emit_run_completed,
    emit_run_started,
    emit_step_completed,
    emit_step_failed,
    emit_step_started,
    run_events,
)
from app.pipeline.events.sinks import NatsPublishSink
from app.pipeline.events.step_trace import StepTraceSink, set_trace_sink, reset_trace_sink
from app.pipeline.events.types import _now_iso
from app.pipeline.runbook import start
from app.pipeline.services.deps import ActLive, PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.services.account_repository import AccountRepository, current_interval_slot_key
from app.services.copied_references import copied_reference_exclude_set
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.pipeline_progress import progress_active, progress_done, progress_error
from app.services.pipeline_spec_repository import PipelineSpecRepository
from app.models.pipeline_spec import PipelineSpecDocument
from app.pipeline.spec.validator import validate_spec
from app.pipeline.spec.compiler import compile_spec
from app.pipeline.spec.catalog import get_tool_catalog

logger = logging.getLogger(__name__)

__all__ = [
    "TickContext",
    "TickMode",
    "build_tick_context",
    "current_interval_slot_key",
    "run_account_pipeline",
    "run_interval_tick",
]


def _slot_spec_status(slot: str, mode: TickMode) -> str:
    """Run the challenger on 1-in-N slots so a staged variant accrues its own
    attribution rows; the rest run the champion. Pure function of the slot string
    + a fixed cron job — NOT a per-agent scheduler. Forced (manual) ticks always
    run the champion: a human force-post must not silently land on a variant."""
    if mode != "scheduled":
        return "champion"
    every = max(2, int(settings.challenger_slot_every))
    bucket = int(slot.replace("-", ""))  # deterministic integer index from the slot
    return "challenger" if (bucket % every == 0) else "champion"


def _load_spec_for_status(
    account_id: str, status: str, repo: PipelineSpecRepository
) -> PipelineSpecDocument:
    """Champion slot → the live champion (or seeded baseline). Challenger slot →
    the staged challenger if one exists, else fall back to champion-or-baseline.
    Uses ONLY doc 04's repo API (load / load_or_default); no new repo method."""
    if status == "challenger":
        challenger = repo.load(account_id, "challenger")  # None when unstaged
        if challenger is not None:
            return challenger
    return repo.load_or_default(account_id)  # champion or baseline


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
    spec_status = _slot_spec_status(slot, mode)  # NEW — single clock read, no drift
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
        spec_status=spec_status,  # NEW — derived from slot
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
            "spec_status": spec_status,
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
    started_iso = _now_iso()
    trace = StepTraceSink(
        run_id=run_id, account_id=account.account_id, slot=ctx.slot,
        mode=ctx.mode, niche=account.category or "", started_at=started_iso,
    )
    token = set_trace_sink(trace)
    with run_events(
        run_id=run_id,
        account_id=account.account_id,
        slot=ctx.slot,
        mode=ctx.mode,
        sinks=[NatsPublishSink(), trace],
    ):
        emit_run_started(niche=account.category or "")
        status = "error"
        try:
            out = _run_account_pipeline(ctx, account, run_id=run_id)
            status = _run_status_from_out(out)
            return out
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            emit_run_completed(
                status=status, duration_ms=duration_ms
            )
            trace.finalize(status=status, duration_ms=duration_ms, ended_at=_now_iso())
            reset_trace_sink(token)


def engine_invariants(*, meter: CostMeter) -> tuple:
    """Build the engine-injected invariant wrappers (cost ceiling + guardian assertion).

    Args:
        meter: The CostMeter for this run.

    Returns:
        A tuple of StepWrapper functions to inject into run_steps.
    """

    def cost_wrapper(flat, run_fn):
        def _run(ctx, deps):
            meter.check_before(flat.id)  # raises CostCeilingExceeded if over budget
            res = run_fn(ctx, deps)
            meter.record_after(flat.id, drain_run_llm_cost_usd())  # tally this leaf's LLM spend
            return res

        return _run

    def guardian_wrapper(flat, run_fn):
        def _run(ctx, deps):
            res = run_fn(ctx, deps)
            if flat.id == "compose_until_safe" and not ctx.has_artifact(ArtifactKey.SAFETY_VERDICT):
                raise RuntimeError("guardian invariant violated: compose wrote no SAFETY_VERDICT")
            return res

        return _run

    return (cost_wrapper, guardian_wrapper)


def _first_failure_reason(result) -> str:
    """Extract the first skip/error reason from a RunbookResult.

    Args:
        result: A RunbookResult from run_steps.

    Returns:
        The skip_reason or error message from the first failed step, or a default.
    """
    for entry in result.steps:
        if entry.get("skipped"):
            return entry.get("skip_reason") or "reference_phase_failed"
        if not entry.get("ok"):
            return entry.get("error") or entry.get("skip_reason") or "reference_phase_failed"
    return "reference_phase_failed"


def _result_from_run(
    ctx: TickContext, account: AccountDocument, run_ctx, result, spec, outcomes
) -> dict[str, Any]:
    """Map terminal artifacts back to the legacy runner return dict.

    Args:
        ctx: The TickContext.
        account: The AccountDocument.
        run_ctx: The TickRunContext after the spec walk.
        result: The RunbookResult from run_steps.
        spec: The loaded PipelineSpecDocument.
        outcomes: The PipelineOutcomeRepository.

    Returns:
        A dict in the legacy shape: skipped/rejected/error/success.
    """
    aid = account.account_id

    # A SENSE step skipped (e.g., no reference with URLs) → skipped run.
    if not result.ok:
        reason = _first_failure_reason(result)
        out = {"account_id": aid, "skipped": reason}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason=reason)
        return out

    verdict = run_ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)
    if verdict is None or not verdict.approved:
        reason = (verdict.last_reject if verdict else None) or "all_compose_attempts_failed"
        out = {
            "account_id": aid,
            "rejected": reason,
            "references_tried": verdict.references_tried if verdict else 0,
        }
        outcomes.append(account_id=aid, phase="runner", status="rejected", reason=reason)
        return out

    published = run_ctx.get_artifact(ArtifactKey.PUBLISHED_POST)
    if published is None or not published.posted:
        reason = (published.skipped_reason if published else None) or "publish_missing"
        out = {"account_id": aid, "error": reason}
        outcomes.append(account_id=aid, phase="runner", status="error", reason=reason)
        return out

    # CC-4: return the FULL finalize_post dict carried on PublishedPost.result verbatim.
    # It already has the legacy shape {account_id, tweet:<full tw_result>, regeneration_round,
    # note?, creation_metrics?}, so the COMPLETE `tweet` object survives.
    out = dict(published.result)
    outcomes.append(account_id=aid, phase="runner", status="ok")
    return out


def _run_account_pipeline(ctx: TickContext, account: AccountDocument, *, run_id: str) -> dict[str, Any]:
    aid = account.account_id
    outcomes = PipelineOutcomeRepository()
    trace_step(
        aid,
        "pre_tick_input",
        {"account_id": aid, "niche": account.category, "slot": ctx.slot, "mode": ctx.mode},
        handoff_to="reload_account",
    )

    # === Guards (verbatim from today, lines 173–218) ===
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
            handoff_to="spec_load_validate_compile",
        )

        # === Load + validate + compile the account's pipeline ONCE ===
        spec = _load_spec_for_status(aid, ctx.spec_status, PipelineSpecRepository())
        catalog = get_tool_catalog()
        report = validate_spec(spec, catalog)
        if not report.ok:
            codes = report.codes()
            out = {
                "account_id": aid,
                "error": f"invalid_spec:{codes[0] if codes else 'unknown'}",
            }
            outcomes.append(
                account_id=aid,
                phase="runner",
                status="error",
                reason="invalid_spec",
                details={"errors": [e.model_dump() for e in report.errors]},
            )
            trace_step(aid, "spec_error", out, handoff_to="(end)")
            return out

        graph = compile_spec(spec, catalog=catalog)

        # === One context for the WHOLE graph ===
        run_ctx = start(aid, niche=account.category, mode=ctx.mode, slot=ctx.slot)
        run_ctx.run_id = run_id  # the wrapper's minted id, == current_run_id()

        deps = post_run_deps_from_tick(ctx)
        deps.live = ActLive(
            account=account,
            tick_ctx=ctx,
            guardian=ctx.guardian,
            twitter=deps.twitter,            # CC-7: == tick_ctx.twitter (required ActLive handle)
            post_registry=deps.post_registry,  # CC-7: == tick_ctx.post_registry
            run_id=run_id,
            pipeline_hash=spec.version_hash,
            copied_exclude=copied_reference_exclude_set(account),
            max_regeneration_rounds=ctx.max_regeneration_rounds,
            bypass_post_cooldown=ctx.bypass_post_cooldown,
        )

        # === Walk SENSE + ACT in one synchronous pass ===
        meter = CostMeter(run_id=run_id, ceiling_usd=settings.pipeline_cost_ceiling_usd)
        result = run_steps(
            graph,
            run_ctx,
            deps,
            wrappers=engine_invariants(meter=meter),
        )

        return _result_from_run(ctx, account, run_ctx, result, spec, outcomes)
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

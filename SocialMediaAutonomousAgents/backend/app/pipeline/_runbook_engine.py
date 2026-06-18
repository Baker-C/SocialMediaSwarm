"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable, Sequence

from app.pipeline.events.capture import capture_artifacts
from app.pipeline.events.dispatcher import (
    emit_step_completed,
    emit_step_failed,
    emit_step_skipped,
    emit_step_started,
)
from app.pipeline.events.step_trace import record_step_trace
from app.pipeline.events.types import _now_iso
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import FlatStep, Step, StepFn, flatten_steps
from app.pipeline.types.tool import StepResult
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.pipeline_progress import progress_active, progress_done, progress_error

logger = logging.getLogger(__name__)

# A leaf wrapper sees the about-to-run step and returns a (possibly) wrapped run fn.
StepWrapper = Callable[[FlatStep, StepFn], StepFn]


class RunbookResult:
    def __init__(self, ctx: TickRunContext, steps: list[dict]) -> None:
        self.ctx = ctx
        self.steps = steps
        self.ok = all(s.get("ok", False) or s.get("skipped") for s in steps)

    def reference_context(self) -> dict:
        return {
            "timeline": self.ctx.get("timeline_analysis"),
            "own_posts": self.ctx.get("own_posts_analysis"),
            "timeline_ranked": self.ctx.get("timeline_ranked"),
            "own_posts_ranked": self.ctx.get("own_posts_ranked"),
        }


def _run_step_with_progress(
    flat: FlatStep,
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    wrappers: Sequence[StepWrapper] = (),
) -> tuple[StepResult, dict]:
    step = flat.step
    progress_active(
        flat.id,
        step.purpose or None,
        scope="runbook",
        parent_id=flat.parent_id,
        purpose=step.purpose or None,
    )
    inputs = capture_artifacts(ctx, tuple(step.reads) + tuple(step.reads_optional))
    emit_step_started(
        flat.id,
        scope="runbook",
        parent_id=flat.parent_id,
        purpose=step.purpose or None,
        inputs=inputs,
    )
    started = time.monotonic()
    started_iso = _now_iso()

    # Apply wrappers to the step function (outermost wrapper runs first)
    run_fn = step.run
    for wrap in wrappers:
        run_fn = wrap(flat, run_fn)

    try:
        result = run_fn(ctx, deps)
    except Exception as exc:
        logger.exception("runbook step %s failed", flat.id)
        progress_error(flat.id, "step_exception", scope="runbook")
        err = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        emit_step_failed(
            flat.id,
            scope="runbook",
            parent_id=flat.parent_id,
            error=err,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        entry = {
            "id": flat.id,
            "ok": False,
            "error": str(exc),
            "reads": [r.value for r in step.reads],
            "writes": [w.value for w in step.writes],
            "parent_id": flat.parent_id,
        }
        record_step_trace(flat=flat, ctx=ctx, result=StepResult(ok=False, errors=[str(exc)]),
                          status="error", skip_reason=None, error=err,
                          started_at=started_iso, ended_at=_now_iso(),
                          duration_ms=int((time.monotonic() - started) * 1000))
        return StepResult(ok=False, errors=[str(exc)]), entry

    if not isinstance(result, StepResult):
        result = StepResult(ok=True, payload={"value": result})

    duration_ms = int((time.monotonic() - started) * 1000)

    entry = {
        "id": flat.id,
        "ok": result.ok,
        "skipped": result.skipped,
        "skip_reason": result.skip_reason,
        "errors": result.errors,
        "reads": [r.value for r in step.reads],
        "writes": [w.value for w in step.writes],
        "parent_id": flat.parent_id,
        "purpose": step.purpose,
    }

    if result.skipped:
        progress_done(
            flat.id,
            step.purpose or None,
            scope="runbook",
            parent_id=flat.parent_id,
            purpose=step.purpose or None,
        )
        emit_step_skipped(
            flat.id,
            scope="runbook",
            parent_id=flat.parent_id,
            skip_reason=result.skip_reason,
            duration_ms=duration_ms,
        )
    elif result.ok:
        progress_done(
            flat.id,
            step.purpose or None,
            scope="runbook",
            parent_id=flat.parent_id,
            purpose=step.purpose or None,
        )
        emit_step_completed(
            flat.id,
            scope="runbook",
            parent_id=flat.parent_id,
            purpose=step.purpose or None,
            outputs=capture_artifacts(ctx, tuple(step.writes)),
            duration_ms=duration_ms,
        )
    else:
        progress_error(flat.id, result.skip_reason or "step_failed", scope="runbook")
        emit_step_failed(
            flat.id,
            scope="runbook",
            parent_id=flat.parent_id,
            error={"type": "StepFailed", "message": result.skip_reason or "step_failed"},
            duration_ms=duration_ms,
        )

    status = "skipped" if result.skipped else ("ok" if result.ok else "error")
    record_step_trace(flat=flat, ctx=ctx, result=result, status=status,
                      skip_reason=result.skip_reason, error=None,
                      started_at=started_iso, ended_at=_now_iso(), duration_ms=duration_ms)
    return result, entry


def run_steps(
    steps: Sequence[Step],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
    wrappers: Sequence[StepWrapper] = (),
) -> RunbookResult:
    log: list[dict] = []
    outcomes = PipelineOutcomeRepository()
    flat_steps: list[FlatStep] = flatten_steps(steps)

    for flat in flat_steps:
        step = flat.step
        result, entry = _run_step_with_progress(flat, ctx, deps, wrappers=wrappers)
        log.append(entry)

        if not result.ok and not result.skipped and "error" in entry:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{flat.id}",
                status="error",
                reason="step_exception",
                details={"error": entry.get("error")},
            )
            if stop_on_fail:
                break
            continue

        if result.skipped:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{flat.id}",
                status="skipped",
                reason=result.skip_reason,
            )
        elif not result.ok:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{flat.id}",
                status="error",
                reason=result.skip_reason or "step_failed",
                details={"errors": list(result.errors or [])},
            )

        if stop_on_fail and not result.ok and not result.skipped:
            break

    return RunbookResult(ctx, log)

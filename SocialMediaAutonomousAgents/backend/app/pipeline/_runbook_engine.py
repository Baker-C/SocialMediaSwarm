"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import FlatStep, Step, flatten_steps
from app.pipeline.types.tool import StepResult
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.pipeline_progress import progress_active, progress_done, progress_error

logger = logging.getLogger(__name__)


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
) -> tuple[StepResult, dict]:
    step = flat.step
    progress_active(
        flat.id,
        step.purpose or None,
        scope="runbook",
        parent_id=flat.parent_id,
        purpose=step.purpose or None,
    )
    try:
        result = step.run(ctx, deps)
    except Exception as exc:
        logger.exception("runbook step %s failed", flat.id)
        progress_error(flat.id, "step_exception", scope="runbook")
        entry = {
            "id": flat.id,
            "ok": False,
            "error": str(exc),
            "reads": [r.value for r in step.reads],
            "writes": [w.value for w in step.writes],
            "parent_id": flat.parent_id,
        }
        return StepResult(ok=False, errors=[str(exc)]), entry

    if not isinstance(result, StepResult):
        result = StepResult(ok=True, payload={"value": result})

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

    if result.skipped or result.ok:
        progress_done(
            flat.id,
            step.purpose or None,
            scope="runbook",
            parent_id=flat.parent_id,
            purpose=step.purpose or None,
        )
    else:
        progress_error(flat.id, result.skip_reason or "step_failed", scope="runbook")

    return result, entry


def run_steps(
    steps: Sequence[Step],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
) -> RunbookResult:
    log: list[dict] = []
    outcomes = PipelineOutcomeRepository()
    flat_steps: list[FlatStep] = flatten_steps(steps)

    for flat in flat_steps:
        step = flat.step
        result, entry = _run_step_with_progress(flat, ctx, deps)
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

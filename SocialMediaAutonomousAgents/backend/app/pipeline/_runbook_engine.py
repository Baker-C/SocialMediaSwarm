"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import FlatStep, Step, flatten_steps
from app.pipeline.types.tool import StepResult
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

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
        step_id = flat.id
        step = flat.step
        try:
            result = step.run(ctx, deps)
        except Exception as exc:
            logger.exception("runbook step %s failed", step_id)
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason="step_exception",
                details={"error": str(exc)},
            )
            entry = {
                "id": step_id,
                "ok": False,
                "error": str(exc),
                "reads": [r.value for r in step.reads],
                "writes": [w.value for w in step.writes],
                "parent_id": flat.parent_id,
            }
            log.append(entry)
            if stop_on_fail:
                break
            continue

        if not isinstance(result, StepResult):
            result = StepResult(ok=True, payload={"value": result})

        entry = {
            "id": step_id,
            "ok": result.ok,
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "errors": result.errors,
            "reads": [r.value for r in step.reads],
            "writes": [w.value for w in step.writes],
            "parent_id": flat.parent_id,
            "purpose": step.purpose,
        }
        log.append(entry)
        if result.skipped:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="skipped",
                reason=result.skip_reason,
            )
        elif not result.ok:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason=result.skip_reason or "step_failed",
                details={"errors": list(result.errors or [])},
            )

        if stop_on_fail and not result.ok and not result.skipped:
            break

    return RunbookResult(ctx, log)

"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]


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
    steps: Sequence[tuple[str, StepFn]],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
) -> RunbookResult:
    log: list[dict] = []
    for step_id, fn in steps:
        try:
            result = fn(ctx, deps)
        except Exception as exc:
            logger.exception("runbook step %s failed", step_id)
            entry = {"id": step_id, "ok": False, "error": str(exc)}
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
        }
        log.append(entry)

        if stop_on_fail and not result.ok and not result.skipped:
            break

    return RunbookResult(ctx, log)

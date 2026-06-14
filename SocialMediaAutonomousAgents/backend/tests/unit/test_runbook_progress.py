"""Runbook step progress emission."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.pipeline._runbook_engine import run_steps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import Step
from app.pipeline.types.tool import StepResult
from app.pipeline.services.deps import PostRunDeps
from app.services.pipeline_progress import PipelineProgressEvent, run_with_progress


@pytest.fixture
def tick_ctx() -> TickRunContext:
    return TickRunContext(account_id="acct1", niche="news", mode="force", slot="2026-06-12-12-00")


def test_run_steps_emits_progress_for_each_flat_step(tick_ctx: TickRunContext) -> None:
    events: list[PipelineProgressEvent] = []

    def capture(event: PipelineProgressEvent) -> None:
        events.append(event)

    def ok_step(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
        return StepResult(ok=True)

    steps = (
        Step("load_account_bundle", ok_step, purpose="Load bundle"),
        Step("merge_external_references", ok_step, purpose="Merge refs"),
    )

    def _run() -> None:
        run_steps(steps, tick_ctx, MagicMock(spec=PostRunDeps))

    run_with_progress(capture, _run)

    runbook_events = [e for e in events if e.scope == "runbook"]
    assert [e.step_id for e in runbook_events if e.status == "active"] == [
        "load_account_bundle",
        "merge_external_references",
    ]
    assert [e.step_id for e in runbook_events if e.status == "done"] == [
        "load_account_bundle",
        "merge_external_references",
    ]

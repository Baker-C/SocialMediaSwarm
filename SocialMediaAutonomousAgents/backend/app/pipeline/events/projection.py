"""Fold a pipeline event stream into a PipelineRunDocument (pure function)."""

from __future__ import annotations

from collections.abc import Iterable

from app.models.pipeline_run import PipelineRunDocument, PipelineStepRecord, StepError
from app.pipeline.events.types import PipelineEvent


def _step_key(data: dict) -> str:
    return f"{data.get('scope', '')}:{data.get('step_id', '')}"


def build_run_document(events: Iterable[PipelineEvent]) -> PipelineRunDocument | None:
    """Reconstruct a run's materialized state from its (unordered) event stream."""
    ordered = sorted(events, key=lambda e: e.seq)
    if not ordered:
        return None

    first = ordered[0]
    run = PipelineRunDocument(
        run_id=first.run_id,
        account_id=first.account_id,
        slot=first.slot,
        mode=first.mode,
    )
    steps: dict[str, PipelineStepRecord] = {}
    order: list[str] = []

    def _ensure(data: dict, occurred_at: str) -> PipelineStepRecord:
        key = _step_key(data)
        rec = steps.get(key)
        if rec is None:
            rec = PipelineStepRecord(
                step_id=data.get("step_id", ""),
                scope=data.get("scope", "runbook"),
                parent_id=data.get("parent_id"),
                purpose=data.get("purpose"),
                started_at=occurred_at,
            )
            steps[key] = rec
            order.append(key)
        return rec

    for ev in ordered:
        data = ev.data or {}
        if ev.kind == "run_started":
            run.started_at = ev.occurred_at
            run.niche = data.get("niche") or run.niche
        elif ev.kind == "step_started":
            rec = _ensure(data, ev.occurred_at)
            rec.started_at = ev.occurred_at
            rec.status = "active"
            rec.purpose = rec.purpose or data.get("purpose")
            rec.inputs = data.get("inputs") or rec.inputs
        elif ev.kind == "step_completed":
            rec = _ensure(data, ev.occurred_at)
            rec.status = "ok"
            rec.ended_at = ev.occurred_at
            rec.duration_ms = data.get("duration_ms")
            rec.outputs = data.get("outputs") or rec.outputs
            rec.purpose = rec.purpose or data.get("purpose")
        elif ev.kind == "step_skipped":
            rec = _ensure(data, ev.occurred_at)
            rec.status = "skipped"
            rec.ended_at = ev.occurred_at
            rec.duration_ms = data.get("duration_ms")
            rec.skip_reason = data.get("skip_reason")
        elif ev.kind == "step_failed":
            rec = _ensure(data, ev.occurred_at)
            rec.status = "error"
            rec.ended_at = ev.occurred_at
            rec.duration_ms = data.get("duration_ms")
            err = data.get("error") or {}
            rec.error = StepError(
                type=err.get("type", ""),
                message=err.get("message", ""),
                traceback=err.get("traceback", ""),
                occurred_at=ev.occurred_at,
            )
        elif ev.kind == "run_completed":
            run.ended_at = ev.occurred_at
            run.status = data.get("status", "ok")
            run.duration_ms = data.get("duration_ms")
            run.summary = data.get("summary") or {}

    run.steps = [steps[key] for key in order]
    run.step_count = len(run.steps)
    return run

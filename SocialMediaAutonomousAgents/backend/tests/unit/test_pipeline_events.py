"""Unit tests for event-sourced pipeline run tracking (no NATS server required)."""

from __future__ import annotations

from app.core.config import settings
from app.pipeline.events import capture as capture_mod
from app.pipeline.events.capture import capture_artifacts
from app.pipeline.events.dispatcher import (
    emit_event,
    emit_run_completed,
    emit_run_started,
    emit_step_completed,
    emit_step_failed,
    emit_step_started,
    run_events,
)
from app.pipeline.events.projection import build_run_document
from app.pipeline.events.sinks import InMemorySink
from app.pipeline.events.types import PipelineEvent
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext


def _events_for_simple_run(sink: InMemorySink):
    with run_events(run_id="run1", account_id="acc1", slot="slot1", mode="force", sinks=[sink]):
        emit_run_started(niche="ai")
        emit_step_started("load", scope="orchestrator", inputs=[{"artifact": "x"}])
        emit_step_completed("load", scope="orchestrator", outputs=[{"artifact": "y"}], duration_ms=12)
        emit_run_completed(status="ok", duration_ms=34)


def test_dispatcher_assigns_increasing_seq_and_envelope():
    sink = InMemorySink()
    _events_for_simple_run(sink)
    assert [e.seq for e in sink.events] == [1, 2, 3, 4]
    assert [e.kind for e in sink.events] == [
        "run_started",
        "step_started",
        "step_completed",
        "run_completed",
    ]
    for e in sink.events:
        assert e.run_id == "run1"
        assert e.account_id == "acc1"
        assert e.mode == "force"
        assert e.occurred_at  # stamped


def test_emit_is_noop_without_dispatcher():
    # Should not raise when no run_events context is active.
    emit_event("step_started", {"step_id": "nope"})
    emit_step_failed("nope", scope="runbook", error={"message": "x"})


def test_event_subject_and_msg_id():
    ev = PipelineEvent(run_id="abc", account_id="a", slot="s", seq=7, kind="step_started")
    assert ev.subject() == "pipeline.run.abc.step_started"
    assert ev.msg_id() == "abc-7"


def test_projection_folds_steps_with_timing_io_and_status():
    sink = InMemorySink()
    with run_events(run_id="r2", account_id="acc2", slot="slotA", mode="scheduled", sinks=[sink]):
        emit_run_started(niche="crypto")
        emit_step_started("fetch", scope="runbook", inputs=[{"artifact": "in1"}, {"artifact": "in2"}])
        emit_step_completed(
            "fetch", scope="runbook", outputs=[{"artifact": "out1"}], duration_ms=50
        )
        emit_step_started("rank", scope="runbook")
        emit_step_failed(
            "rank",
            scope="runbook",
            error={"type": "ValueError", "message": "boom", "traceback": "tb"},
            duration_ms=7,
        )
        emit_run_completed(status="error", duration_ms=80)

    run = build_run_document(sink.events)
    assert run is not None
    assert run.run_id == "r2"
    assert run.account_id == "acc2"
    assert run.niche == "crypto"
    assert run.status == "error"
    assert run.duration_ms == 80
    assert run.step_count == 2

    fetch, rank = run.steps
    assert fetch.step_id == "fetch" and fetch.status == "ok"
    assert fetch.started_at and fetch.ended_at and fetch.duration_ms == 50
    assert len(fetch.inputs) == 2 and len(fetch.outputs) == 1

    assert rank.step_id == "rank" and rank.status == "error"
    assert rank.error is not None
    assert rank.error.type == "ValueError"
    assert rank.error.message == "boom"
    assert rank.error.occurred_at  # stamped from the event


def test_projection_empty_stream_returns_none():
    assert build_run_document([]) is None


def test_capture_metadata_only_when_payloads_disabled(monkeypatch):
    key = ArtifactKey.ACCOUNT_BUNDLE
    ctx = TickRunContext(account_id="a", slot="s")
    ctx.data[key.value] = {"hello": "world"}

    monkeypatch.setattr(settings, "pipeline_capture_payloads", False)
    [entry] = capture_artifacts(ctx, (key,))
    assert entry["artifact"] == key.value
    assert entry["present"] is True
    assert entry["size_bytes"] > 0
    assert "value" not in entry


def test_capture_includes_value_and_truncates(monkeypatch):
    key = ArtifactKey.ACCOUNT_BUNDLE
    ctx = TickRunContext(account_id="a", slot="s")
    ctx.data[key.value] = {"big": "x" * (capture_mod._MAX_JSON_CHARS + 500)}

    monkeypatch.setattr(settings, "pipeline_capture_payloads", True)
    [entry] = capture_artifacts(ctx, (key,))
    assert entry["present"] is True
    assert entry["truncated"] is True
    assert "truncated" in entry["value"]


def test_capture_marks_absent_artifact():
    ctx = TickRunContext(account_id="a", slot="s")
    [entry] = capture_artifacts(ctx, (ArtifactKey.OWN_POSTS,))
    assert entry["present"] is False
    assert "value" not in entry

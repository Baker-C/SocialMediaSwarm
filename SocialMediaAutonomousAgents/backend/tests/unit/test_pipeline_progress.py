"""Pipeline progress event helpers."""

from __future__ import annotations

from app.services.pipeline_progress import (
    PipelineProgressEvent,
    emit,
    progress_active,
    progress_done,
    run_with_progress,
)


def test_emit_noop_without_callback() -> None:
    emit(PipelineProgressEvent("load_account", "Loading account", "active"))


def test_run_with_progress_emits_start() -> None:
    events: list[PipelineProgressEvent] = []

    def capture(event: PipelineProgressEvent) -> None:
        events.append(event)

    def _run() -> str:
        progress_active("load_account")
        progress_done("load_account")
        return "ok"

    result = run_with_progress(capture, _run)
    assert result == "ok"
    assert events[0].step_id == "start"
    assert events[0].status == "active"
    assert events[1].step_id == "start"
    assert events[1].status == "done"
    assert any(e.step_id == "load_account" and e.status == "active" for e in events)
    assert any(e.step_id == "load_account" and e.status == "done" for e in events)


def test_legacy_callback_adapter() -> None:
    seen: list[tuple[str, str, str]] = []

    def legacy(step_id: str, label: str, status: str) -> None:
        seen.append((step_id, label, status))

    run_with_progress(legacy, lambda: None)
    assert seen[0][0] == "start"
    assert seen[0][2] == "active"

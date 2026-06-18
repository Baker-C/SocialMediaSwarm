"""Unit tests for full-fidelity step trace (untruncated capture, in-process sink)."""

from __future__ import annotations

import pytest

from app.models.step_output import StepLink, StepOutputArtifact, StepOutputDocument
from app.models.pipeline_run import PipelineRunDocument
from app.pipeline.events.step_trace import (
    StepTraceSink,
    capture_artifacts_full,
    record_step_trace,
)
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.step_output_repository import StepOutputRepository
from app.services.pipeline_run_repository import PipelineRunRepository


class MockStepOutputRepository(StepOutputRepository):
    """In-memory repository for testing."""

    def __init__(self) -> None:
        self.saved_docs: dict[str, StepOutputDocument] = {}

    def save(self, doc: StepOutputDocument) -> str:
        doc_id = StepOutputDocument.document_id(doc.run_id, doc.step_id)
        self.saved_docs[doc_id] = doc
        return doc_id

    def get(self, run_id: str, step_id: str) -> StepOutputDocument | None:
        doc_id = StepOutputDocument.document_id(run_id, step_id)
        return self.saved_docs.get(doc_id)


class MockPipelineRunRepository(PipelineRunRepository):
    """In-memory repository for testing."""

    def __init__(self) -> None:
        self.saved_runs: dict[str, PipelineRunDocument] = {}

    def save(self, run: PipelineRunDocument) -> str:
        doc_id = PipelineRunDocument.document_id(run.run_id)
        self.saved_runs[doc_id] = run
        return doc_id

    def get(self, run_id: str) -> PipelineRunDocument | None:
        doc_id = PipelineRunDocument.document_id(run_id)
        return self.saved_runs.get(doc_id)


def test_step_output_artifact_absent():
    """Test artifact capture when not present."""
    artifact = StepOutputArtifact(artifact="timeline_references", present=False)
    assert artifact.artifact == "timeline_references"
    assert artifact.present is False
    assert artifact.size_bytes is None
    assert artifact.value is None


def test_step_output_artifact_present():
    """Test artifact capture when present."""
    value = {"key": "value"}
    artifact = StepOutputArtifact(
        artifact="timeline_references", present=True, size_bytes=14, value=value
    )
    assert artifact.artifact == "timeline_references"
    assert artifact.present is True
    assert artifact.size_bytes == 14
    assert artifact.value == value


def test_step_output_document_id():
    """Test document ID generation."""
    doc_id = StepOutputDocument.document_id("run_123", "load_account_bundle")
    assert doc_id == "stepoutputs/run_123/load_account_bundle"


def test_capture_artifacts_full_empty_context():
    """Test full artifact capture with no artifacts present."""
    ctx = TickRunContext(account_id="acc1", slot="slot1")
    artifacts = capture_artifacts_full(ctx, (ArtifactKey.TIMELINE_REFERENCES,))
    assert len(artifacts) == 1
    assert artifacts[0].artifact == "timeline_references"
    assert artifacts[0].present is False


def test_capture_artifacts_full_with_value():
    """Test full artifact capture with large payload (no truncation)."""
    ctx = TickRunContext(account_id="acc1", slot="slot1")
    large_value = [{"text": "x" * 10000}] * 10  # > 8000 chars
    ctx.set("timeline_references", large_value)

    artifacts = capture_artifacts_full(ctx, (ArtifactKey.TIMELINE_REFERENCES,))
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.artifact == "timeline_references"
    assert artifact.present is True
    assert artifact.value == large_value  # Full, untruncated
    assert artifact.size_bytes is not None
    assert artifact.size_bytes > 8000  # Confirm it's large


def test_step_trace_sink_basic_save():
    """Test StepTraceSink saves a step document."""
    step_repo = MockStepOutputRepository()
    run_repo = MockPipelineRunRepository()

    sink = StepTraceSink(
        run_id="run_123",
        account_id="acc1",
        slot="slot1",
        mode="scheduled",
        step_repo=step_repo,
        run_repo=run_repo,
    )

    doc = StepOutputDocument(
        run_id="run_123",
        account_id="acc1",
        step_id="load_account_bundle",
        status="ok",
    )

    sink.on_step(doc)

    # Verify step was saved with seq incremented
    assert doc.seq == 1
    saved = step_repo.get("run_123", "load_account_bundle")
    assert saved is not None
    assert saved.seq == 1
    assert saved.status == "ok"

    # Verify link was added
    assert len(sink._links) == 1
    link = sink._links[0]
    assert link.step_id == "load_account_bundle"
    assert link.seq == 1
    assert link.doc_id == "stepoutputs/run_123/load_account_bundle"


def test_step_trace_sink_multiple_steps():
    """Test StepTraceSink with multiple steps (ordered seq)."""
    step_repo = MockStepOutputRepository()
    run_repo = MockPipelineRunRepository()

    sink = StepTraceSink(
        run_id="run_123",
        account_id="acc1",
        slot="slot1",
        mode="scheduled",
        step_repo=step_repo,
        run_repo=run_repo,
    )

    for i in range(3):
        doc = StepOutputDocument(
            run_id="run_123",
            account_id="acc1",
            step_id=f"step_{i}",
            status="ok",
        )
        sink.on_step(doc)

    # Verify all steps saved with correct seq
    for i in range(3):
        saved = step_repo.get("run_123", f"step_{i}")
        assert saved is not None
        assert saved.seq == i + 1

    # Verify links ordered by seq
    assert len(sink._links) == 3
    for i, link in enumerate(sink._links):
        assert link.step_id == f"step_{i}"
        assert link.seq == i + 1


def test_step_trace_sink_finalize():
    """Test StepTraceSink finalizes run header with ordered links."""
    step_repo = MockStepOutputRepository()
    run_repo = MockPipelineRunRepository()

    sink = StepTraceSink(
        run_id="run_123",
        account_id="acc1",
        slot="slot1",
        mode="scheduled",
        niche="news",
        started_at="2024-01-01T00:00:00",
        step_repo=step_repo,
        run_repo=run_repo,
    )

    # Add two steps
    for i in range(2):
        doc = StepOutputDocument(
            run_id="run_123",
            account_id="acc1",
            step_id=f"step_{i}",
            status="ok",
            duration_ms=100 * (i + 1),
        )
        sink.on_step(doc)

    # Finalize
    sink.finalize(status="ok", duration_ms=300, ended_at="2024-01-01T00:00:30")

    # Verify run header saved
    saved_run = run_repo.get("run_123")
    assert saved_run is not None
    assert saved_run.status == "ok"
    assert saved_run.duration_ms == 300
    assert saved_run.ended_at == "2024-01-01T00:00:30"
    assert saved_run.step_count == 2
    assert len(saved_run.step_links) == 2
    assert saved_run.step_links[0].step_id == "step_0"
    assert saved_run.step_links[1].step_id == "step_1"
    assert saved_run.niche == "news"


def test_step_trace_sink_error_handling():
    """Test StepTraceSink swallows exceptions and logs them."""

    class FailingRepository(StepOutputRepository):
        def save(self, doc: StepOutputDocument) -> str:
            raise RuntimeError("Database error")

    sink = StepTraceSink(
        run_id="run_123",
        account_id="acc1",
        slot="slot1",
        mode="scheduled",
        step_repo=FailingRepository(),
    )

    doc = StepOutputDocument(
        run_id="run_123",
        account_id="acc1",
        step_id="test_step",
        status="ok",
    )

    # Should not raise; error is logged and swallowed
    sink.on_step(doc)

    # Verify no links were added (save failed)
    assert len(sink._links) == 0


def test_step_link_model():
    """Test StepLink model."""
    link = StepLink(
        step_id="test_step",
        scope="runbook",
        seq=1,
        status="ok",
        duration_ms=100,
        doc_id="stepoutputs/run_123/test_step",
    )
    assert link.step_id == "test_step"
    assert link.scope == "runbook"
    assert link.seq == 1
    assert link.status == "ok"
    assert link.duration_ms == 100
    assert link.doc_id == "stepoutputs/run_123/test_step"


def test_pipeline_run_document_with_step_links():
    """Test PipelineRunDocument includes step_links field."""
    run = PipelineRunDocument(
        run_id="run_123",
        account_id="acc1",
        slot="slot1",
    )
    assert run.step_links == []

    # Add links
    run.step_links = [
        StepLink(
            step_id="step_0",
            seq=1,
            status="ok",
            doc_id="stepoutputs/run_123/step_0",
        ),
    ]
    assert len(run.step_links) == 1
    assert run.step_links[0].step_id == "step_0"


def test_step_output_document_with_error():
    """Test StepOutputDocument with error details."""
    error_dict = {
        "type": "ValueError",
        "message": "Invalid input",
        "traceback": "Traceback ...",
    }
    doc = StepOutputDocument(
        run_id="run_123",
        account_id="acc1",
        step_id="failed_step",
        status="error",
        error=error_dict,
    )
    assert doc.status == "error"
    assert doc.error == error_dict
    assert doc.error["type"] == "ValueError"


def test_step_output_document_with_artifacts():
    """Test StepOutputDocument with inputs/outputs artifacts."""
    inputs = [
        StepOutputArtifact(artifact="timeline_references", present=True, value=[]),
        StepOutputArtifact(artifact="search_references", present=False),
    ]
    outputs = [
        StepOutputArtifact(artifact="summary", present=True, value={"text": "..."})
    ]
    doc = StepOutputDocument(
        run_id="run_123",
        account_id="acc1",
        step_id="summarize_step",
        inputs=inputs,
        outputs=outputs,
    )
    assert len(doc.inputs) == 2
    assert doc.inputs[0].artifact == "timeline_references"
    assert doc.inputs[1].present is False
    assert len(doc.outputs) == 1
    assert doc.outputs[0].artifact == "summary"

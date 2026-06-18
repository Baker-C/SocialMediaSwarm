"""Full-fidelity per-step trace documents (untruncated step I/O).

Each pipeline step's COMPLETE input + output is stored as its own RavenDB
document (collection StepOutputs, id stepoutputs/{run_id}/{step_id}). The run
header (PipelineRunDocument) carries an ORDERED list of links to these docs.
Separate-doc-per-step is how we keep full fidelity without an unbounded run doc.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepOutputArtifact(BaseModel):
    """One captured artifact (an input read or an output write) of a step.

    Mirrors the dict shape emitted by capture_artifacts() (capture.py:39-45) but
    `value` is ALWAYS the full untruncated payload (no 8000-char cap, no gate).
    """

    artifact: str                       # ArtifactKey.value, e.g. "timeline_references"
    present: bool
    size_bytes: int | None = None
    value: Any | None = None            # full JSON-able payload; None only if absent


class StepOutputDocument(BaseModel):
    """Complete trace of ONE step execution. Document id: stepoutputs/{run_id}/{step_id}."""

    run_id: str
    account_id: str
    step_id: str                        # dotted flat id, e.g. "summarize_for_compose.analyze_own_posts.rank_own_posts"
    scope: str = "runbook"              # runbook | orchestrator (see §8 for orchestrator phases)
    parent_id: str | None = None
    purpose: str | None = None
    seq: int = 0                        # execution order within the run (1-based)
    status: str = "ok"                  # ok | skipped | error
    skip_reason: str | None = None
    error: dict[str, Any] | None = None # {type, message, traceback} on failure
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    inputs: list[StepOutputArtifact] = Field(default_factory=list)   # full reads + reads_optional
    outputs: list[StepOutputArtifact] = Field(default_factory=list)  # full writes
    result_payload: dict[str, Any] = Field(default_factory=dict)     # StepResult.payload (tool.py:14)

    @staticmethod
    def document_id(run_id: str, step_id: str) -> str:
        return f"stepoutputs/{run_id}/{step_id}"


class StepLink(BaseModel):
    """Ordered pointer from the run header to one StepOutputDocument."""

    step_id: str
    scope: str = "runbook"
    seq: int = 0
    status: str = "ok"
    duration_ms: int | None = None
    doc_id: str                         # stepoutputs/{run_id}/{step_id}

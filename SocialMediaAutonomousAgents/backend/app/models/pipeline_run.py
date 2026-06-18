"""Materialized projection of a pipeline run, folded from the event stream."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.step_output import StepLink


class StepError(BaseModel):
    type: str = ""
    message: str = ""
    traceback: str = ""
    occurred_at: str = ""


class PipelineStepRecord(BaseModel):
    step_id: str
    scope: str = "runbook"  # orchestrator | runbook
    parent_id: str | None = None
    purpose: str | None = None
    status: str = "active"  # active | ok | skipped | error
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    skip_reason: str | None = None
    error: StepError | None = None


class PipelineRunDocument(BaseModel):
    run_id: str
    account_id: str
    slot: str
    mode: str = "scheduled"
    niche: str = ""
    status: str = "running"  # running | ok | skipped | rejected | error
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    step_count: int = 0
    steps: list[PipelineStepRecord] = Field(default_factory=list)
    step_links: list[StepLink] = Field(default_factory=list)  # NEW: ordered links to StepOutputDocument
    summary: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def document_id(run_id: str) -> str:
        return f"pipelineruns/{run_id}"

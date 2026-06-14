"""Canonical pipeline event envelope (event-sourced run tracking)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

EventKind = Literal[
    "run_started",
    "step_started",
    "step_completed",
    "step_skipped",
    "step_failed",
    "run_completed",
]

StepScope = Literal["orchestrator", "runbook"]

EVENT_SUBJECT_PREFIX = "pipeline.run"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineEvent(BaseModel):
    """One immutable event in a pipeline run's stream.

    The ``data`` bag carries kind-specific fields (step_id, inputs, outputs,
    error, status, ...) so the envelope stays stable as the system grows.
    """

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    account_id: str
    slot: str
    mode: str = "scheduled"
    seq: int = 0
    occurred_at: str = Field(default_factory=_now_iso)
    kind: EventKind
    data: dict[str, Any] = Field(default_factory=dict)

    def subject(self, prefix: str = EVENT_SUBJECT_PREFIX) -> str:
        """JetStream subject: ``pipeline.run.{run_id}.{kind}`` (run_id is uuid hex)."""
        return f"{prefix}.{self.run_id}.{self.kind}"

    def msg_id(self) -> str:
        """Dedupe id for JetStream (``Nats-Msg-Id`` header)."""
        return f"{self.run_id}-{self.seq}"

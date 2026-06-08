"""Outcome ledger for pipeline and jobs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineOutcomeDocument(BaseModel):
    account_id: str
    phase: str
    status: str
    created_at: str
    reason: str | None = None
    details: dict = Field(default_factory=dict)

    @staticmethod
    def document_id(account_id: str, phase: str, created_at: str) -> str:
        slug = created_at.replace(":", "").replace(".", "").replace("+", "")
        return f"pipelineoutcomes/{account_id}-{phase}-{slug}"

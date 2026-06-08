"""Persistence helper for pipeline outcomes."""

from __future__ import annotations

from datetime import datetime, timezone

from app.infrastructure.ravendb_http import RavenDBHttpClient, get_ravendb_client
from app.models.pipeline_outcome import PipelineOutcomeDocument

PIPELINE_OUTCOME_COLLECTION = "PipelineOutcomes"


class PipelineOutcomeRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def append(
        self,
        *,
        account_id: str,
        phase: str,
        status: str,
        reason: str | None = None,
        details: dict | None = None,
    ) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        doc = PipelineOutcomeDocument(
            account_id=account_id,
            phase=phase,
            status=status,
            created_at=created_at,
            reason=reason,
            details=details or {},
        )
        doc_id = PipelineOutcomeDocument.document_id(account_id, phase, created_at)
        self.client.put_document(doc_id, doc.model_dump(exclude_none=True), collection=PIPELINE_OUTCOME_COLLECTION)
        return doc_id

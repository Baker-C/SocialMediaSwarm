"""Persistence for full-fidelity step output documents (RavenDB collection StepOutputs)."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.step_output import StepOutputDocument

logger = logging.getLogger(__name__)

STEP_OUTPUT_COLLECTION = "StepOutputs"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_meta(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class StepOutputRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, doc: StepOutputDocument) -> str:
        doc_id = StepOutputDocument.document_id(doc.run_id, doc.step_id)
        # Unconditional PUT keyed by {run_id}/{step_id} → idempotent: a replay
        # overwrites the same doc, never duplicates (no CAS needed). See Decision Defense.
        self.client.put_document(
            doc_id, doc.model_dump(exclude_none=True), collection=STEP_OUTPUT_COLLECTION
        )
        return doc_id

    def get(self, run_id: str, step_id: str) -> StepOutputDocument | None:
        raw = self.client.get_document(StepOutputDocument.document_id(run_id, step_id))
        if raw is None:
            return None
        try:
            return StepOutputDocument.model_validate(_strip_meta(raw))
        except Exception as exc:
            logger.debug("StepOutputs get invalid doc %s/%s: %s", run_id, step_id, exc)
            return None

    def list_for_run(self, run_id: str, *, limit: int = 200) -> list[StepOutputDocument]:
        rid = _safe_rql_string(run_id)
        if not rid:
            return []
        cap = max(1, min(int(limit), 500))
        rql = f'from {STEP_OUTPUT_COLLECTION} where run_id == "{rid}" order by seq limit {cap}'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("StepOutputs query failed: %s", exc)
            return []
        out: list[StepOutputDocument] = []
        for raw in rows:
            try:
                out.append(StepOutputDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("StepOutputs skip invalid row: %s", exc)
        return out

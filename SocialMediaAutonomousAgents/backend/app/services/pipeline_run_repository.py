"""Persistence for materialized pipeline run projections (RavenDB)."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.pipeline_run import PipelineRunDocument

logger = logging.getLogger(__name__)

PIPELINE_RUN_COLLECTION = "PipelineRuns"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_meta(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class PipelineRunRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, run: PipelineRunDocument) -> str:
        doc_id = PipelineRunDocument.document_id(run.run_id)
        self.client.put_document(
            doc_id, run.model_dump(exclude_none=True), collection=PIPELINE_RUN_COLLECTION
        )
        return doc_id

    def get(self, run_id: str) -> PipelineRunDocument | None:
        raw = self.client.get_document(PipelineRunDocument.document_id(run_id))
        if raw is None:
            return None
        try:
            return PipelineRunDocument.model_validate(_strip_meta(raw))
        except Exception as exc:
            logger.debug("PipelineRuns get invalid doc %s: %s", run_id, exc)
            return None

    def _query(self, where: str, limit: int) -> list[PipelineRunDocument]:
        cap = max(1, min(int(limit), 500))
        clause = f" where {where}" if where else ""
        rql = f"from {PIPELINE_RUN_COLLECTION}{clause} order by started_at desc limit {cap}"
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("PipelineRuns query failed: %s", exc)
            return []
        out: list[PipelineRunDocument] = []
        for raw in rows:
            try:
                out.append(PipelineRunDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("PipelineRuns skip invalid row: %s", exc)
        return out

    def list_for_account(self, account_id: str, *, limit: int = 100) -> list[PipelineRunDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        return self._query(f'account_id == "{aid}"', limit)

    def list_fleet(
        self,
        *,
        limit: int = 100,
        account_id: str | None = None,
        status: str | None = None,
    ) -> list[PipelineRunDocument]:
        clauses: list[str] = []
        if account_id:
            aid = _safe_rql_string(account_id)
            if aid:
                clauses.append(f'account_id == "{aid}"')
        if status:
            st = _safe_rql_string(status)
            if st:
                clauses.append(f'status == "{st}"')
        return self._query(" and ".join(clauses), limit)

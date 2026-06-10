"""Persistence helper for pipeline outcomes."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.pipeline_outcome import PipelineOutcomeDocument

logger = logging.getLogger(__name__)


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)

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

    def list_for_account(
        self,
        account_id: str,
        *,
        since: str | None = None,
        limit: int = 200,
        phase: str | None = None,
        status: str | None = None,
    ) -> list[PipelineOutcomeDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        cap = max(1, min(int(limit), 500))
        clauses = [f'account_id == "{aid}"']
        if phase:
            p = _safe_rql_string(phase)
            if p:
                clauses.append(f'phase == "{p}"')
        if status:
            s = _safe_rql_string(status)
            if s:
                clauses.append(f'status == "{s}"')
        where = " and ".join(clauses)
        rql = f"from PipelineOutcomes where {where} order by created_at desc limit {cap}"
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(
                    f'from @all where startsWith(id(), "pipelineoutcomes/{aid}-") '
                    f"order by created_at desc limit {cap}"
                )
            except RavenDBHttpError as exc:
                logger.warning("PipelineOutcomes list_for_account failed %s: %s", account_id, exc)
                return []

        out: list[PipelineOutcomeDocument] = []
        for raw in rows:
            stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            if since:
                created = str(stripped.get("created_at") or "")
                if created and created < since:
                    continue
            if phase and stripped.get("phase") != phase:
                continue
            if status and stripped.get("status") != status:
                continue
            try:
                out.append(PipelineOutcomeDocument.model_validate(stripped))
            except Exception as exc:
                logger.debug("PipelineOutcomes skip invalid row: %s", exc)
        return out

    def list_fleet(
        self,
        *,
        since: str | None = None,
        limit: int = 200,
        account_id: str | None = None,
        phase: str | None = None,
        status: str | None = None,
    ) -> list[PipelineOutcomeDocument]:
        """Pipeline outcomes across accounts (newest first)."""
        cap = max(1, min(int(limit), 500))
        clauses: list[str] = []
        if account_id:
            aid = _safe_rql_string(account_id)
            if aid:
                clauses.append(f'account_id == "{aid}"')
        if phase:
            p = _safe_rql_string(phase)
            if p:
                clauses.append(f'phase == "{p}"')
        if status:
            s = _safe_rql_string(status)
            if s:
                clauses.append(f'status == "{s}"')
        where = f" where {' and '.join(clauses)}" if clauses else ""
        rql = f"from PipelineOutcomes{where} order by created_at desc limit {cap}"
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(f"from PipelineOutcomes order by created_at desc limit {cap}")
            except RavenDBHttpError as exc:
                logger.warning("PipelineOutcomes list_fleet failed: %s", exc)
                return []

        out: list[PipelineOutcomeDocument] = []
        for raw in rows:
            stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            if account_id and stripped.get("account_id") != account_id:
                continue
            if since:
                created = str(stripped.get("created_at") or "")
                if created and created < since:
                    continue
            if phase and stripped.get("phase") != phase:
                continue
            if status and stripped.get("status") != status:
                continue
            try:
                out.append(PipelineOutcomeDocument.model_validate(stripped))
            except Exception as exc:
                logger.debug("PipelineOutcomes skip invalid row: %s", exc)
        return out[:cap]

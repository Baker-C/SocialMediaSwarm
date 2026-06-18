"""Persistence for pipeline spec revisions."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.pipeline_revision import PipelineRevisionDocument

logger = logging.getLogger(__name__)


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


PIPELINE_REVISION_COLLECTION = "PipelineRevisions"


class PipelineRevisionRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, revision: PipelineRevisionDocument) -> str:
        doc_id = PipelineRevisionDocument.document_id(revision.account_id, revision.seq)
        self.client.put_document(
            doc_id, revision.model_dump(exclude_none=True), collection=PIPELINE_REVISION_COLLECTION
        )
        return doc_id

    def list_for_account(self, account_id: str) -> list[PipelineRevisionDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        rql = f'from PipelineRevisions where account_id == "{aid}" order by seq asc'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(
                    f'from @all where startsWith(id(), "pipelinerevisions/{aid}-") order by seq asc'
                )
            except RavenDBHttpError as exc:
                logger.warning("PipelineRevisions list_for_account failed %s: %s", account_id, exc)
                return []

        out: list[PipelineRevisionDocument] = []
        for raw in rows:
            try:
                stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
                out.append(PipelineRevisionDocument.model_validate(stripped))
            except Exception as exc:
                logger.debug("PipelineRevisions skip invalid row: %s", exc)
        return out

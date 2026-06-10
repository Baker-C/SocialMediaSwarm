"""Persistence for account voice revisions."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.voice_revision import VoiceRevisionDocument

logger = logging.getLogger(__name__)


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)

VOICE_REVISION_COLLECTION = "VoiceRevisions"


class VoiceRevisionRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, revision: VoiceRevisionDocument) -> str:
        doc_id = VoiceRevisionDocument.document_id(revision.account_id, revision.seq)
        self.client.put_document(doc_id, revision.model_dump(exclude_none=True), collection=VOICE_REVISION_COLLECTION)
        return doc_id

    def list_for_account(self, account_id: str) -> list[VoiceRevisionDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        rql = f'from VoiceRevisions where account_id == "{aid}" order by seq asc'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(
                    f'from @all where startsWith(id(), "voicerevisions/{aid}-") order by seq asc'
                )
            except RavenDBHttpError as exc:
                logger.warning("VoiceRevisions list_for_account failed %s: %s", account_id, exc)
                return []

        out: list[VoiceRevisionDocument] = []
        for raw in rows:
            try:
                stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
                out.append(VoiceRevisionDocument.model_validate(stripped))
            except Exception as exc:
                logger.debug("VoiceRevisions skip invalid row: %s", exc)
        return out

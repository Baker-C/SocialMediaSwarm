"""Persistence for account voice revisions."""

from __future__ import annotations

from app.infrastructure.ravendb_http import RavenDBHttpClient, get_ravendb_client
from app.models.voice_revision import VoiceRevisionDocument

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

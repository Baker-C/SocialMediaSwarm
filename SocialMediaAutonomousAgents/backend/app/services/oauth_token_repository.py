"""Persist runtime OAuth2 tokens and PKCE sessions in RavenDB."""

from __future__ import annotations

from datetime import datetime, timezone

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.oauth_token import OAuthSessionDocument, OAuthTokenDocument


def _strip_metadata(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not str(k).startswith("@")}


class OAuthTokenRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def load_token(self, account_id: str) -> OAuthTokenDocument | None:
        raw = self.client.get_document(OAuthTokenDocument.document_id(account_id))
        if raw is None:
            return None
        return OAuthTokenDocument.model_validate(_strip_metadata(raw))

    def save_token(self, token: OAuthTokenDocument) -> None:
        doc_id = OAuthTokenDocument.document_id(token.account_id)
        self.client.put_document(doc_id, token.model_dump(exclude_none=True), collection="OAuthTokens")

    def delete_token(self, account_id: str) -> None:
        doc_id = OAuthTokenDocument.document_id(account_id)
        try:
            self.client.delete_document(doc_id)
        except RavenDBHttpError:
            pass

    def list_tokens(self) -> list[OAuthTokenDocument]:
        try:
            rows = self.client.query("from OAuthTokens")
        except RavenDBHttpError:
            rows = self.client.query("from @all where startsWith(id(), 'oauth-tokens/')")
        out: list[OAuthTokenDocument] = []
        for raw in rows:
            try:
                out.append(OAuthTokenDocument.model_validate(_strip_metadata(raw)))
            except Exception:
                continue
        return out

    def has_token(self, account_id: str) -> bool:
        return self.load_token(account_id) is not None

    def save_session(self, session: OAuthSessionDocument) -> None:
        doc_id = OAuthSessionDocument.document_id(session.state)
        self.client.put_document(doc_id, session.model_dump(), collection="OAuthSessions")

    def load_session(self, state: str) -> OAuthSessionDocument | None:
        raw = self.client.get_document(OAuthSessionDocument.document_id(state))
        if raw is None:
            return None
        return OAuthSessionDocument.model_validate(_strip_metadata(raw))

    def delete_session(self, state: str) -> None:
        doc_id = OAuthSessionDocument.document_id(state)
        try:
            self.client.delete_document(doc_id)
        except RavenDBHttpError:
            pass

    def purge_expired_sessions(self) -> int:
        now = datetime.now(timezone.utc)
        removed = 0
        try:
            rows = self.client.query("from OAuthSessions")
        except RavenDBHttpError:
            return 0
        for raw in rows:
            try:
                session = OAuthSessionDocument.model_validate(_strip_metadata(raw))
                exp = datetime.fromisoformat(session.expires_at.replace("Z", "+00:00"))
                if exp <= now:
                    self.delete_session(session.state)
                    removed += 1
            except Exception:
                continue
        return removed

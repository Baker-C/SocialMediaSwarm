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
        token = None
        try:
            token = self.load_token(account_id)
        except RavenDBHttpError:
            token = None
        doc_id = OAuthTokenDocument.document_id(account_id)
        try:
            self.client.delete_document(doc_id)
        except RavenDBHttpError:
            pass
        if token is not None and token.x_user_id:
            self.release_binding(token.x_user_id)

    def find_account_by_x_user_id(self, x_user_id: str) -> str | None:
        """Return the account_id currently holding the binding for ``x_user_id``, or None."""
        uid = (x_user_id or "").strip()
        if not uid:
            return None
        raw = self.client.get_document(self._binding_document_id(uid))
        if raw is None:
            return None
        account_id = _strip_metadata(raw).get("account_id")
        return str(account_id).strip() or None if account_id else None

    @staticmethod
    def _binding_document_id(x_user_id: str) -> str:
        return f"oauth-bindings/{x_user_id}"

    def claim_binding(self, x_user_id: str, account_id: str) -> bool:
        """Atomically claim ``x_user_id`` for ``account_id``.

        Returns True if the binding was created or is already owned by this account,
        False if a different account currently holds it.
        """
        uid = (x_user_id or "").strip()
        aid = (account_id or "").strip()
        if not uid or not aid:
            return False
        doc_id = self._binding_document_id(uid)
        claimed = self.client.put_document(
            doc_id,
            {"x_user_id": uid, "account_id": aid, "updated_at": datetime.now(timezone.utc).isoformat()},
            collection="OAuthBindings",
            create_if_absent=True,
        )
        if claimed:
            return True
        owner = self.find_account_by_x_user_id(uid)
        return owner == aid

    def release_binding(self, x_user_id: str) -> None:
        uid = (x_user_id or "").strip()
        if not uid:
            return
        try:
            self.client.delete_document(self._binding_document_id(uid))
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

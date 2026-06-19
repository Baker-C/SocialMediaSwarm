"""Persist per-account encrypted secrets in RavenDB."""

from __future__ import annotations

from app.infrastructure.ravendb_http import RavenDBHttpClient, get_ravendb_client
from app.models.account_secrets import AccountSecretsDocument


def _strip_metadata(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not str(k).startswith("@")}


class AccountSecretsRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def load(self, account_id: str) -> AccountSecretsDocument | None:
        raw = self.client.get_document(AccountSecretsDocument.document_id(account_id))
        if raw is None:
            return None
        return AccountSecretsDocument.model_validate(_strip_metadata(raw))

    def save(self, doc: AccountSecretsDocument) -> None:
        doc_id = AccountSecretsDocument.document_id(doc.account_id)
        self.client.put_document(
            doc_id,
            doc.model_dump(exclude_none=True),
            collection="AccountSecrets",
        )

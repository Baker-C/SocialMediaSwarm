"""Persist point-in-time account snapshots (collection AccountSnapshots)."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.account_snapshot import AccountSnapshotDocument

logger = logging.getLogger(__name__)

SNAPSHOT_COLLECTION = "AccountSnapshots"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_metadata(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class AccountSnapshotRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, snapshot: AccountSnapshotDocument) -> str:
        doc_id = AccountSnapshotDocument.document_id(snapshot.account_id, snapshot.created_at)
        self.client.put_document(
            doc_id, snapshot.model_dump(exclude_none=True), collection=SNAPSHOT_COLLECTION
        )
        return doc_id

    def list_for_account(self, account_id: str, *, limit: int = 100) -> list[AccountSnapshotDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        cap = max(1, min(int(limit), 500))
        rql = (
            f'from AccountSnapshots where account_id == "{aid}" '
            f"order by created_at desc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(
                    f'from @all where startsWith(id(), "accountsnapshots/{aid}-") '
                    f"order by created_at desc limit {cap}"
                )
            except RavenDBHttpError as exc:
                logger.warning("AccountSnapshots list_for_account failed %s: %s", account_id, exc)
                return []

        out: list[AccountSnapshotDocument] = []
        for raw in rows:
            try:
                out.append(AccountSnapshotDocument.model_validate(_strip_metadata(raw)))
            except Exception as exc:
                logger.debug("AccountSnapshots skip invalid row: %s", exc)
        return out

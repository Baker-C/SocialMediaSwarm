"""RavenDB-backed short-lived lock to block duplicate posts across processes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.infrastructure.ravendb_http import RavenDBHttpClient

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


class PostLockRepository:
    def __init__(self, client: RavenDBHttpClient) -> None:
        self._client = client

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"post-locks/{account_id}"

    def try_acquire(self, account_id: str, *, holder: str, ttl_seconds: int) -> bool:
        doc_id = self.document_id(account_id)
        now = datetime.now(timezone.utc)
        existing = self._client.get_document(doc_id)
        if existing:
            until = _parse_iso(existing.get("until"))
            if until and until > now and existing.get("holder") != holder:
                return False

        until_iso = (now + timedelta(seconds=max(30, ttl_seconds))).isoformat()
        payload: dict[str, Any] = {
            "account_id": account_id,
            "holder": holder,
            "until": until_iso,
            "acquired_at": now.isoformat(),
        }
        self._client.put_document(doc_id, payload, collection="PostLocks")

        verify = self._client.get_document(doc_id)
        return bool(verify and verify.get("holder") == holder)

    def release(self, account_id: str, *, holder: str) -> None:
        doc_id = self.document_id(account_id)
        existing = self._client.get_document(doc_id)
        if not existing or existing.get("holder") != holder:
            return
        now = datetime.now(timezone.utc)
        payload = dict(existing)
        payload["until"] = now.isoformat()
        payload["released_at"] = now.isoformat()
        self._client.put_document(doc_id, payload, collection="PostLocks")

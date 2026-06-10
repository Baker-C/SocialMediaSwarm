"""Persistence for post metric snapshots."""

from __future__ import annotations

import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.post_metric_snapshot import PostMetricSnapshotDocument

POST_METRIC_SNAPSHOT_COLLECTION = "PostMetricSnapshots"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


class PostMetricSnapshotRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, snapshot: PostMetricSnapshotDocument) -> str:
        doc_id = PostMetricSnapshotDocument.document_id(snapshot.account_id, snapshot.tweet_id, snapshot.captured_at)
        self.client.put_document(doc_id, snapshot.model_dump(exclude_none=True), collection=POST_METRIC_SNAPSHOT_COLLECTION)
        return doc_id

    def latest_for_tweet(self, account_id: str, tweet_id: str) -> PostMetricSnapshotDocument | None:
        aid = _safe_rql_string(account_id)
        tid = _safe_rql_string(tweet_id)
        if not aid or not tid:
            return None
        rql = (
            f'from PostMetricSnapshots where account_id == "{aid}" and tweet_id == "{tid}" '
            "order by captured_at desc limit 1"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            rows = []
        if not rows:
            return None
        try:
            raw = {k: v for k, v in rows[0].items() if not str(k).startswith("@")}
            return PostMetricSnapshotDocument.model_validate(raw)
        except Exception:
            return None

    def list_for_tweet(
        self,
        account_id: str,
        tweet_id: str,
        *,
        limit: int = 500,
    ) -> list[PostMetricSnapshotDocument]:
        aid = _safe_rql_string(account_id)
        tid = _safe_rql_string(tweet_id)
        if not aid or not tid:
            return []
        cap = max(1, min(int(limit), 500))
        rql = (
            f'from PostMetricSnapshots where account_id == "{aid}" and tweet_id == "{tid}" '
            f"order by captured_at asc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            rows = []
        out: list[PostMetricSnapshotDocument] = []
        for raw in rows:
            try:
                stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
                out.append(PostMetricSnapshotDocument.model_validate(stripped))
            except Exception:
                continue
        return out

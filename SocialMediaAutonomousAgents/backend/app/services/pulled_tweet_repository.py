"""Persist external reference tweets (collection PulledTweets)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.pulled_tweet import PullRecordStats, PulledTweetDocument
from app.social.tweet_enrichment import enrichment_from_row

logger = logging.getLogger(__name__)

PULLED_COLLECTION = "PulledTweets"
_UPSERT_RETRIES = 3

_METRIC_KEYS = (
    "like_count",
    "reply_count",
    "retweet_count",
    "quote_count",
    "impression_count",
)
_ENRICHMENT_SCALAR_KEYS = (
    "tweet_permalink",
    "primary_media_type",
)


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _resolve_tweet_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("tweet_id") or "").strip()


def _row_to_fields(row: dict[str, Any]) -> dict[str, Any]:
    created = row.get("created_at")
    if created is not None and not isinstance(created, str):
        created = str(created)
    out: dict[str, Any] = {
        "text": row.get("text"),
        "author_id": row.get("author_id"),
        "created_at": created,
        "lang": row.get("lang"),
        "source": str(row.get("source") or ""),
        "trend_query": row.get("trend_query"),
    }
    for key in _METRIC_KEYS:
        val = row.get(key)
        if isinstance(val, int):
            out[key] = val
    out.update(enrichment_from_row(row))
    return out


def _strip_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


def _merge_engagement(base: PulledTweetDocument, row: dict[str, Any]) -> PulledTweetDocument:
    data = base.model_dump()
    fields = _row_to_fields(row)
    merge_keys = (
        "text",
        "author_id",
        "created_at",
        "lang",
        "source",
        "trend_query",
        *_METRIC_KEYS,
        *_ENRICHMENT_SCALAR_KEYS,
        "media_types",
        "embed_urls",
    )
    for key in merge_keys:
        val = fields.get(key)
        if val is not None and val != "":
            data[key] = val
    if fields.get("media"):
        data["media"] = [m.model_dump(exclude_none=True) for m in fields["media"]]
    if fields.get("url_entities"):
        data["url_entities"] = [u.model_dump(exclude_none=True) for u in fields["url_entities"]]
    return PulledTweetDocument.model_validate(data)


class PulledTweetRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def record_pulls(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        account_id: str,
        slot: str,
    ) -> PullRecordStats:
        stats = PullRecordStats()
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if not isinstance(row, dict):
                continue
            tweet_id = _resolve_tweet_id(row)
            if not tweet_id:
                stats.skipped_no_id += 1
                logger.debug("PulledTweets skip row without tweet id account=%s", account_id)
                continue
            is_new = self._upsert_one(
                tweet_id=tweet_id,
                row=row,
                account_id=account_id,
                slot=slot,
                now_iso=now,
            )
            if is_new:
                stats.new_count += 1
            else:
                stats.duplicate_count += 1
        return stats

    def _upsert_one(
        self,
        *,
        tweet_id: str,
        row: dict[str, Any],
        account_id: str,
        slot: str,
        now_iso: str,
    ) -> bool:
        doc_id = PulledTweetDocument.document_id(tweet_id)
        for attempt in range(_UPSERT_RETRIES):
            raw = self.client.get_document(doc_id)
            if raw is None:
                doc = PulledTweetDocument(
                    tweet_id=tweet_id,
                    **_row_to_fields(row),
                    duplicate_fetch_count=0,
                    pull_count=1,
                    first_pulled_at=now_iso,
                    last_pulled_at=now_iso,
                    first_pulled_for_account_id=account_id,
                    last_pulled_for_account_id=account_id,
                    pulled_for_account_ids=[account_id],
                    last_pulled_slot=slot,
                )
                self.client.put_document(
                    doc_id, doc.model_dump(exclude_none=True), collection=PULLED_COLLECTION
                )
                return True

            try:
                existing = PulledTweetDocument.model_validate(_strip_metadata(raw))
            except Exception:
                existing = PulledTweetDocument(
                    tweet_id=tweet_id,
                    first_pulled_at=now_iso,
                    first_pulled_for_account_id=account_id,
                    pulled_for_account_ids=[],
                )

            accounts = list(existing.pulled_for_account_ids)
            if account_id not in accounts:
                accounts.append(account_id)

            updated = _merge_engagement(existing, row)
            data = updated.model_dump()
            data["duplicate_fetch_count"] = existing.duplicate_fetch_count + 1
            data["pull_count"] = existing.pull_count + 1
            data["last_pulled_at"] = now_iso
            data["last_pulled_for_account_id"] = account_id
            data["pulled_for_account_ids"] = accounts
            data["last_pulled_slot"] = slot
            if not data.get("first_pulled_at"):
                data["first_pulled_at"] = now_iso
            if not data.get("first_pulled_for_account_id"):
                data["first_pulled_for_account_id"] = account_id

            self.client.put_document(doc_id, data, collection=PULLED_COLLECTION)
            return False

        logger.warning("PulledTweets upsert gave up after retries tweet_id=%s", tweet_id)
        return False

    def list_for_account(
        self,
        account_id: str,
        *,
        limit: int = 100,
        since: str | None = None,
    ) -> list[PulledTweetDocument]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        cap = max(1, min(int(limit), 500))
        rql = (
            f'from PulledTweets where pulled_for_account_ids any in ("{aid}") '
            f"order by last_pulled_at desc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(
                    f'from @all where startsWith(id(), "pulledtweets/") '
                    f'and pulled_for_account_ids any in ("{aid}") '
                    f"order by last_pulled_at desc limit {cap}"
                )
            except RavenDBHttpError as exc:
                logger.warning("PulledTweets list_for_account failed %s: %s", account_id, exc)
                return []

        out: list[PulledTweetDocument] = []
        for raw in rows:
            stripped = _strip_metadata(raw)
            if since:
                last_at = str(stripped.get("last_pulled_at") or "")
                if last_at and last_at < since:
                    continue
            try:
                out.append(PulledTweetDocument.model_validate(stripped))
            except Exception as exc:
                logger.debug("PulledTweets skip invalid row: %s", exc)
        return out

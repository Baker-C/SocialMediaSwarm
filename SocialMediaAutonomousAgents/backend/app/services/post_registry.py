"""Persist tweet ids per account for engagement polling (collection TrackedPosts)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.metrics.derived import compute_rates
from app.models.tracked_post import PostCreationMetrics, TrackedPostDocument
from app.models.tweet_media import TweetMediaEnrichment
from app.social.tweet_enrichment import enrichment_from_row

logger = logging.getLogger(__name__)

TRACKED_COLLECTION = "TrackedPosts"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


class TrackedPostRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def _query_account_rows(self, account_id: str) -> list[dict]:
        aid = _safe_rql_string(account_id)
        if not aid:
            return []
        rql = f'from TrackedPosts where account_id == "{aid}"'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(f'from @all where startsWith(id(), "trackedposts/{aid}-")')
            except RavenDBHttpError as exc:
                logger.warning("TrackedPosts query failed: %s", exc)
                return []
        return sorted(rows, key=lambda r: str(r.get("posted_at") or ""), reverse=True)

    def list_for_account(self, account_id: str) -> list[dict]:
        """TrackedPost rows for an account, newest first."""
        return self._query_account_rows(account_id)

    def list_tweet_ids(self, account_id: str) -> list[str]:
        ids: list[str] = []
        for r in self._query_account_rows(account_id):
            tid = r.get("tweet_id")
            if isinstance(tid, str) and tid and tid not in ids:
                ids.append(tid)
        return ids

    def totals_for_account(self, account_id: str) -> tuple[int, int]:
        """Sum like_count and impression_count across the account's TrackedPosts.

        Returns ``(total_likes, total_views)`` treating missing metrics as 0.
        """
        aid = _safe_rql_string(account_id)
        if not aid:
            return 0, 0
        rql = f'from TrackedPosts where account_id == "{aid}"'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            try:
                rows = self.client.query(f'from @all where startsWith(id(), "trackedposts/{aid}-")')
            except RavenDBHttpError as exc:
                logger.warning("TrackedPosts totals query failed: %s", exc)
                return 0, 0
        total_likes = 0
        total_views = 0
        for r in rows:
            like = r.get("like_count")
            views = r.get("impression_count")
            if isinstance(like, int):
                total_likes += like
            if isinstance(views, int):
                total_views += views
        return total_likes, total_views

    def record_post(
        self,
        account_id: str,
        tweet_id: str,
        posted_at_iso: str | None = None,
        *,
        creation_metrics: PostCreationMetrics | None = None,
        followers_at_post: int | None = None,
    ) -> None:
        when = posted_at_iso or datetime.now(timezone.utc).isoformat()
        doc = TrackedPostDocument(
            account_id=account_id,
            tweet_id=tweet_id,
            posted_at=when,
            creation_metrics=creation_metrics,
            followers_at_post=followers_at_post,
        )
        doc_id = TrackedPostDocument.document_id(account_id, tweet_id)
        payload = doc.model_dump(exclude_none=True)
        self.client.put_document(doc_id, payload, collection=TRACKED_COLLECTION)

    def update_metrics(self, account_id: str, tweet_id: str, metrics: dict) -> None:
        doc_id = TrackedPostDocument.document_id(account_id, tweet_id)
        raw = self.client.get_document(doc_id)
        if raw is None:
            self.record_post(account_id, tweet_id)
            raw = self.client.get_document(doc_id)
        if raw is None:
            return
        stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
        try:
            base = TrackedPostDocument.model_validate(stripped)
        except Exception:
            base = TrackedPostDocument(account_id=account_id, tweet_id=tweet_id, posted_at=stripped.get("posted_at") or "")
        data = base.model_dump()
        data["last_fetched_at"] = datetime.now(timezone.utc).isoformat()
        data["like_count"] = metrics.get("like_count")
        data["reply_count"] = metrics.get("reply_count")
        data["retweet_count"] = metrics.get("retweet_count")
        data["quote_count"] = metrics.get("quote_count")
        data["impression_count"] = metrics.get("impression_count")
        rates = compute_rates(metrics)
        data["engagement_rate"] = rates.get("engagement_rate")
        data["reply_rate"] = rates.get("reply_rate")
        data["like_rate"] = rates.get("like_rate")
        if metrics.get("profile_click_count") is not None:
            data["profile_click_count"] = metrics.get("profile_click_count")
        if metrics.get("follower_delta") is not None:
            data["follower_delta"] = metrics.get("follower_delta")
        if metrics.get("engagement_velocity") is not None:
            data["engagement_velocity"] = metrics.get("engagement_velocity")
        if base.followers_at_post is not None:
            data["followers_at_post"] = base.followers_at_post
        data["raw_metrics"] = {
            k: v
            for k, v in metrics.items()
            if k
            in (
                "id",
                "text",
                "like_count",
                "impression_count",
                "reply_count",
                "retweet_count",
                "quote_count",
                "profile_click_count",
            )
        }
        self.client.put_document(doc_id, data, collection=TRACKED_COLLECTION)
        if metrics.get("tweet_permalink") or metrics.get("media_types") or metrics.get("embed_urls"):
            self.update_enrichment(account_id, tweet_id, metrics)

    def update_enrichment(self, account_id: str, tweet_id: str, enrichment: TweetMediaEnrichment | dict) -> None:
        """Merge media/embed fields onto an existing TrackedPost (or create stub)."""
        if isinstance(enrichment, dict):
            fields = enrichment_from_row(enrichment)
        else:
            fields = {
                "tweet_permalink": enrichment.tweet_permalink,
                "primary_media_type": enrichment.primary_media_type,
                "media_types": list(enrichment.media_types),
                "media": list(enrichment.media),
                "embed_urls": list(enrichment.embed_urls),
                "url_entities": list(enrichment.url_entities),
            }
        doc_id = TrackedPostDocument.document_id(account_id, tweet_id)
        raw = self.client.get_document(doc_id)
        if raw is None:
            self.record_post(account_id, tweet_id)
            raw = self.client.get_document(doc_id)
        if raw is None:
            return
        stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
        try:
            base = TrackedPostDocument.model_validate(stripped)
        except Exception:
            base = TrackedPostDocument(account_id=account_id, tweet_id=tweet_id)
        data = base.model_dump()
        if fields.get("tweet_permalink"):
            data["tweet_permalink"] = fields["tweet_permalink"]
        if fields.get("primary_media_type"):
            data["primary_media_type"] = fields["primary_media_type"]
        if fields.get("media_types"):
            data["media_types"] = fields["media_types"]
        if fields.get("media"):
            data["media"] = [m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else m for m in fields["media"]]
        if fields.get("embed_urls"):
            data["embed_urls"] = fields["embed_urls"]
        if fields.get("url_entities"):
            data["url_entities"] = [
                u.model_dump(exclude_none=True) if hasattr(u, "model_dump") else u for u in fields["url_entities"]
            ]
        self.client.put_document(doc_id, data, collection=TRACKED_COLLECTION)

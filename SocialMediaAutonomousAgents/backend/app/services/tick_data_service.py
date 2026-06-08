"""Per-tick X data fetch: profile, tracked-post metrics, niche/trend discourse (best-effort)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.reference_tweet_cache import get_cached, set_cached
from app.services.twitter_service import TwitterService
from app.social.exceptions import SocialPlatformError
from app.social.reference_rows import filter_out_own_tweets

logger = logging.getLogger(__name__)


class TickDataService:
    """Aggregates X-backed inputs for the interval content pipeline."""

    def __init__(
        self,
        repo: AccountRepository,
        twitter: TwitterService,
        post_registry: TrackedPostRepository | None = None,
        pulled_tweets: PulledTweetRepository | None = None,
    ) -> None:
        self._repo = repo
        self._twitter = twitter
        self._posts = post_registry
        self._pulled_tweets = pulled_tweets

    def compile_account_bundle(self, account_id: str) -> dict[str, Any]:
        errors: list[str] = []
        profile: dict[str, Any] | None = None
        try:
            profile = self._twitter.get_account_data(account_id)
        except Exception as exc:
            errors.append(f"profile:{exc}")
            logger.warning("TickData profile failed %s: %s", account_id, exc)

        engagements: list[dict[str, Any]] = []
        tweet_ids: list[str] = []
        if self._posts:
            try:
                tweet_ids = self._posts.list_tweet_ids(account_id)
            except Exception as exc:
                errors.append(f"list_tracked:{exc}")
            for tid in tweet_ids:
                try:
                    engagements.append(self._twitter.get_tweet_metrics(account_id, tid))
                except Exception as exc:
                    engagements.append({"tweet_id": tid, "error": str(exc)})
                    logger.warning("TickData metrics %s %s: %s", account_id, tid, exc)

        return {
            "account_id": account_id,
            "profile": profile,
            "tracked_tweet_ids": tweet_ids,
            "post_engagements": engagements,
            "errors": errors,
        }

    def compile_niche_discourse(self, account_id: str, niche: str) -> dict[str, Any]:
        errors: list[str] = []
        trends_dump: dict[str, Any] | None = None
        trend_names: list[str] = []
        trends_source = "none"
        try:
            trends_dump = self._twitter.get_trends(account_id, limit=20)
            trends_source = str((trends_dump or {}).get("source") or "none")
            for t in (trends_dump or {}).get("trends") or []:
                if isinstance(t, dict) and t.get("name"):
                    trend_names.append(str(t["name"]))
        except Exception as exc:
            errors.append(f"trends:{exc}")
            logger.warning("TickData trends failed %s: %s", account_id, exc)

        if trends_source == "personalized":
            trend_ctx = f"personalized X trends for this account: {', '.join(trend_names[:15])}"
        elif trends_source == "woeid":
            woeid = (trends_dump or {}).get("woeid")
            loc = (trends_dump or {}).get("location_name")
            place = f" ({loc})" if loc else (f" (WOEID {woeid})" if woeid else "")
            trend_ctx = f"location trends{place}: {', '.join(trend_names[:15])}"
        else:
            trend_ctx = "no live trends available for this tick"

        summary = (
            f"Account niche: {niche.strip()}. "
            f"{trend_ctx}. "
            "Use as loose topical context; prioritize accuracy over hype."
        )
        return {
            "account_id": account_id,
            "niche": niche,
            "trend_names": trend_names,
            "trends_source": trends_source,
            "trends_raw": trends_dump,
            "discourse_summary": summary,
            "errors": errors,
        }

    def compile_timeline_reference_tweets(
        self,
        account_id: str,
        *,
        authenticated_user_id: str | None,
        slot: str,
    ) -> dict[str, Any]:
        """
        Following home timeline only (up to 100 tweets).

        Own tweets are excluded. TrackedPosts are not used here.
        """
        cached = get_cached(account_id, slot)
        if cached is not None:
            logger.info(
                "timeline_reference cache hit account=%s slot=%s",
                account_id,
                slot,
            )
            return self._finalize_reference_payload(cached, account_id=account_id, slot=slot)

        errors: list[str] = []
        timeline_rows: list[dict[str, Any]] = []

        if settings.following_feed_enabled:
            try:
                timeline_rows = self._twitter.get_following_feed(
                    account_id,
                    max_results=settings.following_timeline_max_results,
                )
            except (SocialPlatformError, ValueError) as exc:
                errors.append(f"following_timeline:{exc}")
                logger.warning("TickData following timeline failed %s: %s", account_id, exc)
        else:
            errors.append("following_feed_disabled")

        timeline_rows = filter_out_own_tweets(timeline_rows, authenticated_user_id)

        payload = {
            "timeline_reference_tweets": timeline_rows,
            "reference_errors": errors,
        }
        payload = self._finalize_reference_payload(payload, account_id=account_id, slot=slot)
        ttl = max(1, int(settings.reference_tweet_cache_minutes)) * 60
        set_cached(account_id, slot, payload, ttl_seconds=float(ttl))
        logger.info(
            "timeline_reference fetched account=%s count=%d",
            account_id,
            len(timeline_rows),
        )
        return payload

    def compile_search_reference_tweets(
        self,
        account_id: str,
        *,
        queries: list[str],
        slot: str,
        authenticated_user_id: str | None = None,
        max_results_per_query: int | None = None,
    ) -> dict[str, Any]:
        """Recent-search reference rows for one or more raw X query strings."""
        normalized: list[str] = []
        seen_q: set[str] = set()
        for raw in queries:
            q = (raw or "").strip()
            if not q or q in seen_q:
                continue
            seen_q.add(q)
            normalized.append(q)

        errors: list[str] = []
        per_query_counts: dict[str, int] = {}
        merged_by_id: dict[str, dict[str, Any]] = {}

        for query in normalized:
            try:
                rows = self._twitter.search_tweets(
                    account_id,
                    query,
                    max_results=max_results_per_query,
                )
            except Exception as exc:
                msg = f"search:{query}:{exc}"
                errors.append(msg)
                logger.warning("TickData search failed %s %s: %s", account_id, query, exc)
                per_query_counts[query] = 0
                continue

            rows = filter_out_own_tweets(rows, authenticated_user_id)
            per_query_counts[query] = len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tid = str(row.get("id") or row.get("tweet_id") or "").strip()
                if not tid:
                    continue
                tagged = dict(row)
                tagged["source"] = "search_recent"
                tagged["search_query"] = query
                tagged.setdefault("trend_query", query)
                if tid in merged_by_id:
                    existing = merged_by_id[tid]
                    matched = list(existing.get("matched_queries") or [existing.get("search_query") or ""])
                    if query not in matched:
                        matched.append(query)
                    existing["matched_queries"] = matched
                else:
                    merged_by_id[tid] = tagged

        search_rows = list(merged_by_id.values())
        payload: dict[str, Any] = {
            "search_reference_tweets": search_rows,
            "search_queries": normalized,
            "per_query_counts": per_query_counts,
            "reference_errors": errors,
        }
        if self._pulled_tweets and search_rows:
            stats = self._pulled_tweets.record_pulls(
                search_rows,
                account_id=account_id,
                slot=slot,
            )
            payload["pulled_tweet_stats"] = stats.model_dump()
        logger.info(
            "search_reference fetched account=%s queries=%d tweets=%d",
            account_id,
            len(normalized),
            len(search_rows),
        )
        return payload

    def _finalize_reference_payload(
        self,
        payload: dict[str, Any],
        *,
        account_id: str,
        slot: str,
    ) -> dict[str, Any]:
        out = dict(payload)
        if self._pulled_tweets:
            rows = out.get("timeline_reference_tweets") or []
            stats = self._pulled_tweets.record_pulls(
                list(rows),
                account_id=account_id,
                slot=slot,
            )
            out["pulled_tweet_stats"] = stats.model_dump()
        return out

    @staticmethod
    def merge_reference_pool_rows(*row_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Union reference rows deduped by tweet id (first occurrence wins)."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rows in row_lists:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tid = str(row.get("id") or row.get("tweet_id") or "").strip()
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                out.append(row)
        return out

    @staticmethod
    def merge_reference_pool(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Timeline rows deduped by tweet id."""
        return TickDataService.merge_reference_pool_rows(
            list(payload.get("timeline_reference_tweets") or []),
        )

    def merge_for_prompt(self, account_bundle: dict[str, Any], niche_bundle: dict[str, Any]) -> str:
        acct = dict(account_bundle)
        acct["post_engagements"] = []
        merged = {"account": acct, "niche_context": niche_bundle}
        try:
            return json.dumps(merged, indent=2, default=str)[:12000]
        except TypeError:
            return str(merged)[:12000]

"""Per-tick X data fetch: profile, tracked-post metrics, niche/trend discourse (best-effort)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.twitter_service import TwitterService
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

        # The post tick needs the live profile only. Per-post engagement metrics are
        # polled by the dedicated engagement jobs (and were discarded here anyway —
        # merge_for_prompt blanks post_engagements before the LLM). Re-fetching every
        # tracked post on every tick was the bulk of the account's X API volume.
        tweet_ids: list[str] = []
        if self._posts:
            try:
                tweet_ids = self._posts.list_tweet_ids(account_id)
            except Exception as exc:
                errors.append(f"list_tracked:{exc}")

        return {
            "account_id": account_id,
            "profile": profile,
            "tracked_tweet_ids": tweet_ids,
            "post_engagements": [],
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
                rows = self._twitter.search_tweets_for_trend(
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

"""Live X (Twitter) client via Tweepy — OAuth 2.0 user Bearer."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, TypeVar

import tweepy

from app.social.credentials import XOAuth2UserCredentials, XCredentials
from app.social.dtos import AccountData, CreatedPost, PostData, TrendItem, TrendsResult
from app.social.exceptions import SocialPlatformError
from app.social.reference_rows import post_data_to_reference_row
from app.social.tweet_enrichment import apply_enrichment_to_post_data, enrich_tweet

logger = logging.getLogger(__name__)

_T = TypeVar("_T")
_SERVER_ERROR_MAX_RETRIES = 2
_SERVER_ERROR_BASE_DELAY_SECONDS = 1.0

_REFERENCE_TWEET_FIELDS = [
    "created_at",
    "public_metrics",
    "author_id",
    "lang",
    "text",
    "conversation_id",
    "attachments",
    "entities",
]
_REFERENCE_EXPANSIONS = ["attachments.media_keys"]
_MEDIA_FIELDS = [
    "type",
    "url",
    "preview_image_url",
    "media_key",
    "duration_ms",
    "width",
    "height",
]

def _parse_dt(value: Any) -> datetime | None:
    """X/Tweepy may return ``created_at`` as ``str`` or ``datetime`` depending on version."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=None)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _id_str(value: Any) -> str | None:
    """Normalize X snowflake ids (Tweepy often returns ``int``)."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _metric(obj: Any, key: str) -> int | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get(key)
        return int(v) if v is not None else None
    v = getattr(obj, key, None)
    return int(v) if v is not None else None


def _trend_volume(item: dict[str, Any]) -> int | None:
    for k in ("tweet_volume", "tweet_count", "volume"):
        v = item.get(k)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
    return None


def _trend_name(item: dict[str, Any]) -> str:
    for k in ("name", "trend_name", "topic_name"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


class XTwitterClient:
    """X API via Tweepy — ``SocialMediaClient`` implementation for OAuth2 user context."""

    def __init__(self, creds: XCredentials) -> None:
        if not isinstance(creds, XOAuth2UserCredentials):
            raise SocialPlatformError("X client requires OAuth2 user credentials", vendor="x")
        self._creds = creds
        self._v2 = tweepy.Client(
            bearer_token=creds.access_token.strip(),
            wait_on_rate_limit=True,
        )

    @property
    def _user_auth(self) -> bool:
        """OAuth2 user uses Bearer auth on v2 endpoints."""
        return False

    @staticmethod
    def _http_status(exc: Exception) -> int | None:
        if not isinstance(exc, tweepy.TweepyException):
            return None
        response = getattr(exc, "response", None)
        if response is None:
            return None
        status = getattr(response, "status_code", None) or getattr(response, "status", None)
        return int(status) if status is not None else None

    def _wrap(self, exc: Exception) -> SocialPlatformError:
        status = self._http_status(exc)
        if status == 401:
            return SocialPlatformError(
                "X API authentication failed (401). Access token may be expired.",
                vendor="x",
                cause=exc,
            )
        if status == 403:
            return SocialPlatformError(
                "Insufficient OAuth scopes for this X API endpoint (403). "
                "Reconnect the account with the required scopes.",
                vendor="x",
                cause=exc,
            )
        if status == 429:
            logger.warning("X API rate limit exceeded (429): %s", exc)
            return SocialPlatformError(
                "X API rate limit exceeded (429). Try again later.",
                vendor="x",
                cause=exc,
            )
        if status is not None and status >= 500:
            return SocialPlatformError(
                f"X API server error ({status}).",
                vendor="x",
                cause=exc,
            )
        if isinstance(exc, tweepy.TweepyException):
            return SocialPlatformError(str(exc), vendor="x", cause=exc)
        return SocialPlatformError(str(exc), vendor="x", cause=exc)

    def _execute_with_backoff(self, fn: Callable[[], _T]) -> _T:
        last_exc: Exception | None = None
        for attempt in range(_SERVER_ERROR_MAX_RETRIES + 1):
            try:
                return fn()
            except Exception as exc:
                status = self._http_status(exc)
                if status is not None and status >= 500 and attempt < _SERVER_ERROR_MAX_RETRIES:
                    delay = _SERVER_ERROR_BASE_DELAY_SECONDS * (2**attempt)
                    logger.warning(
                        "X API %s, retrying in %.1fs (attempt %s/%s)",
                        status,
                        delay,
                        attempt + 1,
                        _SERVER_ERROR_MAX_RETRIES,
                    )
                    time.sleep(delay)
                    last_exc = exc
                    continue
                raise self._wrap(exc) from exc
        if last_exc is not None:
            raise self._wrap(last_exc) from last_exc
        raise SocialPlatformError("X API call failed without an exception", vendor="x")

    def get_trends(
        self,
        *,
        woeid: int = 1,
        limit: int = 30,
        prefer_personalized: bool = True,
    ) -> TrendsResult:
        if prefer_personalized:
            personalized = self._get_personalized_trends_v2(limit=limit)
            if personalized.trends:
                return personalized
            logger.info("personalized trends empty or unavailable; falling back to woeid=%s", woeid)

        return self._get_trends_oauth2_v2(woeid=woeid, limit=limit)

    def _parse_trends_v2_payload(
        self,
        payload: dict[str, Any],
        *,
        limit: int,
        source: str,
        woeid: int | None = None,
    ) -> TrendsResult:
        data = payload.get("data")
        if not isinstance(data, list):
            return TrendsResult(woeid=woeid, source="none")
        trends: list[TrendItem] = []
        for raw in data[:limit]:
            if not isinstance(raw, dict):
                continue
            name = _trend_name(raw)
            if not name:
                continue
            trends.append(
                TrendItem(
                    name=name,
                    tweet_volume=_trend_volume(raw),
                    url=raw.get("url") if isinstance(raw.get("url"), str) else None,
                )
            )
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        loc = meta.get("location_name") or meta.get("name")
        return TrendsResult(
            trends=trends,
            location_name=str(loc) if loc else None,
            woeid=woeid,
            source=source if trends else "none",
        )

    def _get_personalized_trends_v2(self, *, limit: int) -> TrendsResult:
        """GET /2/users/personalized_trends — tailored to the authenticated user."""
        ua = self._user_auth
        try:
            r = self._v2.request("GET", "/2/users/personalized_trends", user_auth=ua)
            if r.status_code != 200:
                logger.warning(
                    "OAuth2 personalized trends HTTP %s body=%s",
                    r.status_code,
                    (r.text or "")[:300],
                )
                return TrendsResult(source="none")
            payload = r.json()
            if not isinstance(payload, dict):
                return TrendsResult(source="none")
            return self._parse_trends_v2_payload(payload, limit=limit, source="personalized")
        except Exception as exc:
            logger.warning("OAuth2 personalized trends request failed: %s", exc)
            return TrendsResult(source="none")

    def _get_trends_oauth2_v2(self, *, woeid: int, limit: int) -> TrendsResult:
        """
        WOEID trends via X API v2 (Bearer user token). May return 403 depending on tier.
        """
        ua = self._user_auth
        try:
            r = self._v2.request("GET", f"/2/trends/by/woeid/{woeid}", user_auth=ua)
            if r.status_code != 200:
                logger.warning(
                    "OAuth2 trends HTTP %s woeid=%s body=%s",
                    r.status_code,
                    woeid,
                    (r.text or "")[:300],
                )
                return TrendsResult(woeid=woeid, source="none")
            payload = r.json()
            if not isinstance(payload, dict):
                return TrendsResult(woeid=woeid, source="none")
            return self._parse_trends_v2_payload(payload, limit=limit, source="woeid", woeid=woeid)
        except Exception as exc:
            logger.warning("OAuth2 trends request failed woeid=%s: %s", woeid, exc)
            return TrendsResult(woeid=woeid, source="none")

    def get_account_data(self, *, user_id: str | None = None, username: str | None = None) -> AccountData:
        fields = ["created_at", "description", "public_metrics", "profile_image_url", "verified", "name"]
        ua = self._user_auth
        def _fetch():
            if user_id:
                return self._v2.get_user(id=user_id, user_fields=fields, user_auth=ua)
            if username:
                handle = username.lstrip("@")
                return self._v2.get_user(username=handle, user_fields=fields, user_auth=ua)
            return self._v2.get_me(user_fields=fields, user_auth=ua)

        resp = self._execute_with_backoff(_fetch)
        if not resp or not resp.data:
            raise SocialPlatformError("Empty user response from X", vendor="x")
        u = resp.data
        pm = getattr(u, "public_metrics", None)
        raw: dict[str, Any] | None = None
        ud = getattr(u, "data", None)
        if isinstance(ud, dict):
            raw = ud
        return AccountData(
            id=str(u.id),
            username=str(u.username),
            name=getattr(u, "name", None),
            description=getattr(u, "description", None),
            followers_count=_metric(pm, "followers_count"),
            following_count=_metric(pm, "following_count"),
            tweet_count=_metric(pm, "tweet_count"),
            listed_count=_metric(pm, "listed_count"),
            created_at=_parse_dt(getattr(u, "created_at", None)),
            profile_image_url=getattr(u, "profile_image_url", None),
            verified=getattr(u, "verified", None),
            raw=raw,
        )

    def _tweet_object_to_post_data(self, t: Any) -> PostData:
        pm = getattr(t, "public_metrics", None)
        npm = getattr(t, "non_public_metrics", None)
        td = getattr(t, "data", None)
        raw: dict[str, Any] | None = td if isinstance(td, dict) else None
        profile_click_count = _metric(npm, "user_profile_clicks")
        if profile_click_count is None and isinstance(raw, dict):
            npm_raw = raw.get("non_public_metrics")
            if isinstance(npm_raw, dict):
                profile_click_count = _metric(npm_raw, "user_profile_clicks")
        return PostData(
            id=str(t.id),
            text=getattr(t, "text", None),
            author_id=_id_str(getattr(t, "author_id", None)),
            created_at=_parse_dt(getattr(t, "created_at", None)),
            like_count=_metric(pm, "like_count"),
            reply_count=_metric(pm, "reply_count"),
            retweet_count=_metric(pm, "retweet_count"),
            quote_count=_metric(pm, "quote_count"),
            impression_count=_metric(pm, "impression_count"),
            profile_click_count=profile_click_count,
            lang=getattr(t, "lang", None),
            raw=raw,
        )

    @staticmethod
    def _response_includes(resp: Any) -> Any:
        if resp is None:
            return None
        return getattr(resp, "includes", None)

    def _enrich_post_data(self, post: PostData, t: Any, includes: Any) -> None:
        enrichment = enrich_tweet(t, includes, tweet_id=post.id)
        apply_enrichment_to_post_data(post, enrichment)

    def _tweets_from_response(
        self,
        resp: Any,
        *,
        source: str,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not resp or not resp.data:
            return []
        includes = self._response_includes(resp)
        author_followers = self._author_followers_map(includes)
        rows: list[dict[str, Any]] = []
        for t in resp.data:
            if t is None:
                continue
            post = self._tweet_object_to_post_data(t)
            if not (post.text or "").strip():
                continue
            self._enrich_post_data(post, t, includes)
            row = post_data_to_reference_row(post, source=source, extra=extra)
            aid = _id_str(getattr(t, "author_id", None))
            if aid and aid in author_followers:
                row["author_followers_count"] = author_followers[aid]
            rows.append(row)
        return rows

    @staticmethod
    def _author_followers_map(includes: Any) -> dict[str, int]:
        users = []
        if isinstance(includes, dict):
            users = includes.get("users") or []
        elif hasattr(includes, "users"):
            users = getattr(includes, "users", []) or []
        out: dict[str, int] = {}
        for u in users:
            uid = _id_str(getattr(u, "id", None))
            pm = getattr(u, "public_metrics", None)
            followers = _metric(pm, "followers_count")
            if uid and isinstance(followers, int):
                out[uid] = followers
        return out

    def _reference_tweet_kwargs_tiers(self) -> list[dict[str, Any]]:
        return [
            {
                "tweet_fields": _REFERENCE_TWEET_FIELDS,
                "expansions": [*_REFERENCE_EXPANSIONS, "author_id"],
                "media_fields": _MEDIA_FIELDS,
                "user_fields": ["public_metrics"],
            },
            {
                "tweet_fields": _REFERENCE_TWEET_FIELDS,
                "expansions": _REFERENCE_EXPANSIONS,
                "media_fields": _MEDIA_FIELDS,
            },
            {
                "tweet_fields": _REFERENCE_TWEET_FIELDS[:6],
            },
        ]

    def _fetch_reference_tweets(self, fetcher: Any, *, user_auth: bool) -> list[dict[str, Any]]:
        """Call Tweepy with full→no-author→minimal tiered fallback."""
        tiers = self._reference_tweet_kwargs_tiers()
        last_exc: Exception | None = None
        for idx, tier in enumerate(tiers):
            kwargs = {**tier, "user_auth": user_auth}
            try:
                return fetcher(**kwargs)
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                retryable = "403" in msg or "400" in msg or "forbidden" in msg
                if not retryable:
                    raise self._wrap(exc) from exc
                if idx < len(tiers) - 1:
                    logger.warning("reference tier %d failed; retrying next tier: %s", idx + 1, exc)
                    continue
        if last_exc is not None:
            raise self._wrap(last_exc) from last_exc
        raise SocialPlatformError("reference tweet fetch failed without exception", vendor="x")

    def _fetch_own_tweet(self, post_id: str, *, user_auth: bool) -> Any:
        extended_fields = [*_REFERENCE_TWEET_FIELDS, "non_public_metrics"]
        try:
            return self._v2.get_tweet(
                id=post_id,
                tweet_fields=extended_fields,
                expansions=_REFERENCE_EXPANSIONS,
                media_fields=_MEDIA_FIELDS,
                user_auth=user_auth,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "403" not in msg and "400" not in msg and "forbidden" not in msg:
                raise self._wrap(exc) from exc
            logger.warning("own tweet extended metrics unavailable; retrying public-only: %s", exc)
            try:
                return self._v2.get_tweet(
                    id=post_id,
                    tweet_fields=_REFERENCE_TWEET_FIELDS,
                    expansions=_REFERENCE_EXPANSIONS,
                    media_fields=_MEDIA_FIELDS,
                    user_auth=user_auth,
                )
            except Exception as retry_exc:
                raise self._wrap(retry_exc) from retry_exc

    def search_recent_tweets(
        self,
        query: str,
        *,
        max_results: int = 50,
        sort_order: str = "relevancy",
        trend_query: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recent search (last 7 days). Returns reference rows with ``source=search_recent``."""
        q = (query or "").strip()
        if not q:
            return []
        ua = self._user_auth
        cap = max(10, min(int(max_results), 100))
        resp = self._execute_with_backoff(
            lambda: self._fetch_reference_tweets(
                lambda **kw: self._v2.search_recent_tweets(
                    q, max_results=cap, sort_order=sort_order, **kw
                ),
                user_auth=ua,
            )
        )
        extra = {"trend_query": trend_query or q}
        return self._tweets_from_response(resp, source="search_recent", extra=extra)

    def get_following_timeline_tweets(
        self,
        *,
        max_results: int = 100,
        exclude_retweets: bool = True,
    ) -> list[dict[str, Any]]:
        """Reverse-chronological home timeline for the authenticated user."""
        ua = self._user_auth
        cap = max(1, min(int(max_results), 100))
        exclude = ["retweets"] if exclude_retweets else None
        resp = self._execute_with_backoff(
            lambda: self._fetch_reference_tweets(
                lambda **kw: self._v2.get_home_timeline(
                    max_results=cap, exclude=exclude, **kw
                ),
                user_auth=ua,
            )
        )
        return self._tweets_from_response(resp, source="following_timeline")

    def get_post_data(self, post_id: str) -> PostData:
        ua = self._user_auth
        resp = self._execute_with_backoff(lambda: self._fetch_own_tweet(post_id, user_auth=ua))
        if not resp or not resp.data:
            raise SocialPlatformError(f"Tweet not found: {post_id}", vendor="x")
        post = self._tweet_object_to_post_data(resp.data)
        self._enrich_post_data(post, resp.data, self._response_includes(resp))
        return post

    def create_post(self, text: str) -> CreatedPost:
        ua = self._user_auth
        resp = self._execute_with_backoff(lambda: self._v2.create_tweet(text=text, user_auth=ua))
        if not resp or not resp.data:
            raise SocialPlatformError("Empty response from create_tweet", vendor="x")
        d = resp.data
        tid = str(getattr(d, "id", "") or (d.get("id") if isinstance(d, dict) else "") or "")
        if not tid:
            raise SocialPlatformError("Missing tweet id in create_tweet response", vendor="x")
        return CreatedPost(id=tid, text=text)

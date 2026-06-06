"""Per-account posting and reads via the unified ``SocialMediaService`` (X via Tweepy)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from app.core.config import settings
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.oauth_exceptions import ReauthRequired
from app.services.twitter_oauth2_service import TwitterOAuth2Service
from app.social.credentials import XCredentials, XOAuth2UserCredentials
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from app.social.service import get_social_media_service

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class TwitterService:
    """X reads and posts via ``SocialMediaService`` / Tweepy (OAuth2 only)."""

    def __init__(
        self,
        repo: AccountRepository | None = None,
        oauth: TwitterOAuth2Service | None = None,
    ) -> None:
        self._repo = repo or AccountRepository()
        self._oauth = oauth or TwitterOAuth2Service(account_repo=self._repo)
        self._social = get_social_media_service()

    def _x_credentials(self, acc: AccountDocument, *, auto_refresh: bool = True) -> XCredentials | None:
        return self._oauth.get_credentials(acc.account_id, auto_refresh=auto_refresh)

    def _x_credentials_unavailable_reason(self, acc: AccountDocument) -> str:
        return self._oauth.credentials_unavailable_reason(acc.account_id)

    @staticmethod
    def _is_unauthorized(exc: SocialPlatformError) -> bool:
        cause = exc.cause
        if cause is not None:
            response = getattr(cause, "response", None)
            if response is not None:
                status = getattr(response, "status_code", None) or getattr(response, "status", None)
                if status == 401:
                    return True
        msg = str(exc).lower()
        return "401" in msg or "unauthorized" in msg

    def _require_credentials(self, acc: AccountDocument) -> XCredentials:
        try:
            creds = self._x_credentials(acc, auto_refresh=True)
        except ReauthRequired as exc:
            raise ValueError(str(exc)) from exc
        if creds is None:
            raise ValueError(
                f"Missing or invalid X credentials for account_id={acc.account_id}: "
                f"{self._x_credentials_unavailable_reason(acc)}"
            )
        return creds

    def _call_with_auth_retry(
        self,
        acc: AccountDocument,
        fn: Callable[[XCredentials], _T],
    ) -> _T:
        creds = self._require_credentials(acc)
        try:
            return fn(creds)
        except SocialPlatformError as exc:
            if not self._is_unauthorized(exc):
                raise
            logger.info(
                "X API 401 for account_id=%s; attempting token refresh and one retry",
                acc.account_id,
            )
            try:
                self._oauth.refresh_account_tokens(acc.account_id)
            except ReauthRequired as reauth_exc:
                raise ValueError(str(reauth_exc)) from reauth_exc
            except Exception as refresh_exc:
                raise ValueError(
                    f"X token refresh failed for account_id={acc.account_id}: {refresh_exc}"
                ) from refresh_exc
            creds = self._x_credentials(acc, auto_refresh=False)
            if creds is None:
                raise ValueError(
                    f"X credentials unavailable after refresh for account_id={acc.account_id}"
                )
            return fn(creds)

    def verify_api_health(self, account_id: str) -> list[str]:
        """
        Live X check when decryptable credentials exist: ``get_me`` (or user lookup)
        via the same path as production reads.
        """
        acc = self._repo.load(account_id)
        if acc is None:
            return [f"RavenDB: no account document for account_id={account_id!r}"]
        try:
            self._require_credentials(acc)
        except ValueError as exc:
            return [str(exc)]
        failures: list[str] = []
        try:
            self._call_with_auth_retry(
                acc,
                lambda c: self._social.get_account_data(SocialPlatform.X, c, username=None),
            )
        except (SocialPlatformError, ValueError) as exc:
            msg = str(exc)
            cause = getattr(exc, "cause", None)
            if cause is not None:
                msg = f"{msg} | underlying: {type(cause).__name__}: {cause}"
            failures.append(f"X API: {msg}")
        except Exception as exc:
            failures.append(f"X API: {type(exc).__name__}: {exc}")
        return failures

    def verify_x_connection(self, account_id: str) -> tuple[bool, str]:
        acc = self._repo.load(account_id)
        if acc is None:
            return False, "RavenDB: no account document for this account_id"
        try:
            self._require_credentials(acc)
        except ValueError as exc:
            return False, str(exc)
        try:
            self._call_with_auth_retry(
                acc,
                lambda c: self._social.get_account_data(SocialPlatform.X, c, username=None),
            )
        except (SocialPlatformError, ValueError) as exc:
            msg = str(exc)
            cause = getattr(exc, "cause", None)
            if cause is not None:
                msg = f"{msg} | underlying: {type(cause).__name__}: {cause}"
            return False, msg
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, ""

    def post_tweet(self, account_id: str, text: str) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        created = self._call_with_auth_retry(
            acc,
            lambda c: self._social.create_post(SocialPlatform.X, c, text),
        )
        return {"id": created.id, "text": created.text or text}

    def get_tweet_metrics(self, account_id: str, tweet_id: str) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        post = self._call_with_auth_retry(
            acc,
            lambda c: self._social.get_post_data(SocialPlatform.X, c, tweet_id),
        )
        return post.model_dump()

    def get_trends(
        self,
        account_id: str,
        *,
        woeid: int | None = None,
        limit: int = 30,
        prefer_personalized: bool | None = None,
    ) -> dict:
        from app.core.config import settings

        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        woeid_val = woeid if woeid is not None else settings.trends_fallback_woeid
        prefer = (
            prefer_personalized
            if prefer_personalized is not None
            else settings.trends_prefer_personalized
        )
        trends = self._call_with_auth_retry(
            acc,
            lambda c: self._social.get_trends(
                SocialPlatform.X,
                c,
                woeid=woeid_val,
                limit=limit,
                prefer_personalized=prefer,
            ),
        )
        return trends.model_dump()

    def search_tweets_for_trend(
        self,
        account_id: str,
        trend_name: str,
        *,
        max_results: int | None = None,
    ) -> list[dict]:
        from app.core.config import settings
        from app.social.enums import SocialPlatform
        from app.social.trend_query import build_search_query

        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        query = build_search_query(trend_name)
        if not query:
            return []
        cap = max_results if max_results is not None else settings.trend_search_max_results
        return self._call_with_auth_retry(
            acc,
            lambda c: self._social.search_recent_tweets(
                SocialPlatform.X,
                c,
                query,
                max_results=cap,
                trend_query=trend_name,
            ),
        )

    def get_following_feed(
        self,
        account_id: str,
        *,
        max_results: int | None = None,
    ) -> list[dict]:
        from app.core.config import settings
        from app.social.enums import SocialPlatform

        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        cap = max_results if max_results is not None else settings.following_timeline_max_results
        return self._call_with_auth_retry(
            acc,
            lambda c: self._social.get_following_timeline_tweets(
                SocialPlatform.X,
                c,
                max_results=cap,
            ),
        )

    def get_account_data(self, account_id: str, *, username: str | None = None) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        handle = username if username is not None else (acc.twitter_handle or None)
        data = self._call_with_auth_retry(
            acc,
            lambda c: self._social.get_account_data(
                SocialPlatform.X,
                c,
                username=handle.lstrip("@") if handle else None,
            ),
        )
        return data.model_dump()

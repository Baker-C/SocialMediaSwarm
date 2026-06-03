"""Per-account posting and reads via the unified ``SocialMediaService`` (X via Tweepy)."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.social.credentials import XCredentials, XOAuth2UserCredentials
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from app.social.service import get_social_media_service
from app.utils.encryption import decrypt_value, fernet_from_key

logger = logging.getLogger(__name__)


class TwitterService:
    """X reads and posts via ``SocialMediaService`` / Tweepy (OAuth2 only)."""

    def __init__(self, repo: AccountRepository | None = None) -> None:
        self._repo = repo or AccountRepository()
        self._social = get_social_media_service()

    def _fernet(self):
        if not settings.encryption_key or not settings.encryption_key.strip():
            return None
        return fernet_from_key(settings.encryption_key.strip())

    def _x_credentials(self, acc: AccountDocument) -> XCredentials | None:
        f = self._fernet()
        if f is None:
            logger.warning("ENCRYPTION_KEY missing; cannot decrypt credentials for %s", acc.account_id)
            return None

        o2_enc = (acc.credentials.oauth2_access_token_enc or "").strip()
        if o2_enc:
            try:
                access = decrypt_value(f, o2_enc).strip()
                if access:
                    refresh: str | None = None
                    if acc.credentials.oauth2_refresh_token_enc:
                        r = decrypt_value(f, acc.credentials.oauth2_refresh_token_enc).strip()
                        refresh = r or None
                    return XOAuth2UserCredentials(access_token=access, refresh_token=refresh)
            except ValueError as exc:
                logger.warning("Decrypt failed for OAuth2 fields %s: %s", acc.account_id, exc)
        return None

    def _x_credentials_unavailable_reason(self, acc: AccountDocument) -> str:
        if not settings.encryption_key or not settings.encryption_key.strip():
            return "ENCRYPTION_KEY is missing or empty; cannot decrypt X credentials"
        if (acc.credentials.oauth2_access_token_enc or "").strip():
            return (
                "OAuth2 user access token could not be decrypted "
                "(wrong ENCRYPTION_KEY or corrupt ciphertext)"
            )
        return "missing encrypted OAuth2 access token on account document"

    def verify_api_health(self, account_id: str) -> list[str]:
        """
        Live X check when decryptable credentials exist: ``get_me`` (or user lookup)
        via the same path as production reads.
        """
        acc = self._repo.load(account_id)
        if acc is None:
            return [f"RavenDB: no account document for account_id={account_id!r}"]
        creds = self._x_credentials(acc)
        if creds is None:
            return [self._x_credentials_unavailable_reason(acc)]
        failures: list[str] = []
        try:
            self._social.get_account_data(SocialPlatform.X, creds, username=None)
        except SocialPlatformError as exc:
            msg = str(exc)
            if exc.cause is not None:
                msg = f"{msg} | underlying: {type(exc.cause).__name__}: {exc.cause}"
            failures.append(f"X API: {msg}")
        except Exception as exc:
            failures.append(f"X API: {type(exc).__name__}: {exc}")
        return failures

    def verify_x_connection(self, account_id: str) -> tuple[bool, str]:
        acc = self._repo.load(account_id)
        if acc is None:
            return False, "RavenDB: no account document for this account_id"
        creds = self._x_credentials(acc)
        if creds is None:
            return False, self._x_credentials_unavailable_reason(acc)
        try:
            self._social.get_account_data(SocialPlatform.X, creds, username=None)
        except SocialPlatformError as exc:
            msg = str(exc)
            if exc.cause is not None:
                msg = f"{msg} | underlying: {type(exc.cause).__name__}: {exc.cause}"
            return False, msg
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, ""

    def post_tweet(self, account_id: str, text: str) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(
                f"Missing or invalid X credentials for account_id={account_id}: "
                f"{self._x_credentials_unavailable_reason(acc)}"
            )
        created = self._social.create_post(SocialPlatform.X, creds, text)
        return {"id": created.id, "text": created.text or text}

    def get_tweet_metrics(self, account_id: str, tweet_id: str) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(f"Missing or invalid X credentials for account_id={account_id}")
        post = self._social.get_post_data(SocialPlatform.X, creds, tweet_id)
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
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(f"Missing or invalid X credentials for account_id={account_id}")
        woeid_val = woeid if woeid is not None else settings.trends_fallback_woeid
        prefer = (
            prefer_personalized
            if prefer_personalized is not None
            else settings.trends_prefer_personalized
        )
        trends = self._social.get_trends(
            SocialPlatform.X,
            creds,
            woeid=woeid_val,
            limit=limit,
            prefer_personalized=prefer,
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
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(f"Missing or invalid X credentials for account_id={account_id}")
        query = build_search_query(trend_name)
        if not query:
            return []
        cap = max_results if max_results is not None else settings.trend_search_max_results
        return self._social.search_recent_tweets(
            SocialPlatform.X,
            creds,
            query,
            max_results=cap,
            trend_query=trend_name,
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
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(f"Missing or invalid X credentials for account_id={account_id}")
        cap = max_results if max_results is not None else settings.following_timeline_max_results
        return self._social.get_following_timeline_tweets(
            SocialPlatform.X,
            creds,
            max_results=cap,
        )

    def get_account_data(self, account_id: str, *, username: str | None = None) -> dict:
        acc = self._repo.load(account_id)
        if acc is None:
            raise ValueError(f"Unknown account_id={account_id}")
        creds = self._x_credentials(acc)
        if creds is None:
            raise ValueError(f"Missing or invalid X credentials for account_id={account_id}")
        handle = username if username is not None else (acc.twitter_handle or None)
        data = self._social.get_account_data(
            SocialPlatform.X,
            creds,
            username=handle.lstrip("@") if handle else None,
        )
        return data.model_dump()

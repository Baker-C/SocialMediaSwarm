"""Route social operations by ``SocialPlatform`` to the correct client implementation."""

from __future__ import annotations

from app.social.credentials import XCredentials
from app.social.dtos import AccountData, CreatedPost, PostData, TrendsResult
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from app.social.implementations.x_client import XTwitterClient
from app.social.protocol import SocialMediaClient


class SocialMediaService:
    """
    Facade: pick implementation from ``SocialPlatform`` + credentials.

    Today only ``SocialPlatform.X`` is implemented; new enum values get their
    own branch and DTO mapping layer later.
    """

    def _client(self, platform: SocialPlatform, creds: XCredentials | None) -> SocialMediaClient:
        if creds is None:
            raise SocialPlatformError("X credentials are required for this account.", vendor="x")
        if platform == SocialPlatform.X:
            return XTwitterClient(creds)
        raise SocialPlatformError(f"Unsupported platform: {platform.value}", vendor=platform.value)

    def get_trends(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        *,
        woeid: int = 1,
        limit: int = 30,
        prefer_personalized: bool = True,
    ) -> TrendsResult:
        return self._client(platform, creds).get_trends(
            woeid=woeid,
            limit=limit,
            prefer_personalized=prefer_personalized,
        )

    def get_account_data(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        *,
        user_id: str | None = None,
        username: str | None = None,
    ) -> AccountData:
        return self._client(platform, creds).get_account_data(user_id=user_id, username=username)

    def get_post_data(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        post_id: str,
    ) -> PostData:
        return self._client(platform, creds).get_post_data(post_id)

    def create_post(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        text: str,
    ) -> CreatedPost:
        return self._client(platform, creds).create_post(text)

    def search_recent_tweets(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        query: str,
        *,
        max_results: int = 50,
        sort_order: str = "relevancy",
        trend_query: str | None = None,
    ) -> list[dict]:
        return self._client(platform, creds).search_recent_tweets(
            query,
            max_results=max_results,
            sort_order=sort_order,
            trend_query=trend_query,
        )

    def get_following_timeline_tweets(
        self,
        platform: SocialPlatform,
        creds: XCredentials | None,
        *,
        max_results: int = 100,
        exclude_retweets: bool = True,
    ) -> list[dict]:
        return self._client(platform, creds).get_following_timeline_tweets(
            max_results=max_results,
            exclude_retweets=exclude_retweets,
        )


_social_service: SocialMediaService | None = None


def get_social_media_service() -> SocialMediaService:
    global _social_service
    if _social_service is None:
        _social_service = SocialMediaService()
    return _social_service

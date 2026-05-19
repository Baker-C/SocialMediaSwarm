"""
Structural contract for a social network client.

In Python this is expressed with ``typing.Protocol`` (static duck typing): any
class that defines these methods with compatible signatures can be used
without inheriting from a base class. (An ABC with @abstractmethod is the
nominal alternative.)
"""

from __future__ import annotations

from typing import Protocol

from app.social.dtos import AccountData, CreatedPost, PostData, TrendsResult


class SocialMediaClient(Protocol):
    """Minimum operations the app needs across networks (expand over time)."""

    def get_trends(
        self,
        *,
        woeid: int = 1,
        limit: int = 30,
        prefer_personalized: bool = True,
    ) -> TrendsResult:
        """Trends for the authenticated user; X tries personalized first when enabled."""
        ...

    def get_account_data(
        self,
        *,
        user_id: str | None = None,
        username: str | None = None,
    ) -> AccountData:
        """Current user (both None) or lookup by id or @handle without @."""
        ...

    def get_post_data(self, post_id: str) -> PostData:
        """Single post by vendor id (tweet id on X)."""
        ...

    def create_post(self, text: str) -> CreatedPost:
        """Publish a short-form post (tweet on X)."""
        ...

    def search_recent_tweets(
        self,
        query: str,
        *,
        max_results: int = 50,
        sort_order: str = "relevancy",
        trend_query: str | None = None,
    ) -> list[dict]:
        """Recent search rows (``source=search_recent``)."""
        ...

    def get_following_timeline_tweets(
        self,
        *,
        max_results: int = 100,
        exclude_retweets: bool = True,
    ) -> list[dict]:
        """Home timeline rows (``source=following_timeline``)."""
        ...

"""
Structural contract for a social network client.

In Python this is expressed with ``typing.Protocol`` (static duck typing): any
class that defines these methods with compatible signatures can be used
without inheriting from a base class. (An ABC with @abstractmethod is the
nominal alternative.)
"""

from __future__ import annotations

from typing import Protocol

from app.social.dtos import AccountData, CommentData, CreatedPost, PostData, TrendsResult


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

    def get_posts_data(self, post_ids: list[str]) -> tuple[list[PostData], list[str]]:
        """Batch lookup. Returns ``(found_posts, missing_ids)`` for deleted/unknown ids."""
        ...

    def upload_media(self, data: bytes, mime: str, *, kind: str = "image") -> str:
        """Upload media bytes; return a vendor media id for ``create_post``."""
        ...

    def create_post(self, text: str, *, media_ids: list[str] | None = None) -> CreatedPost:
        """Publish a short-form post (tweet on X), optionally with attached media."""
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

    def like_tweet(self, tweet_id: str) -> dict:
        """Like a tweet. Returns engagement response with success flag."""
        ...

    def unlike_tweet(self, tweet_id: str) -> dict:
        """Unlike a previously liked tweet. Returns engagement response."""
        ...

    def get_tweet_likers(
        self,
        tweet_id: str,
        *,
        max_results: int = 100,
    ) -> list[dict]:
        """Get users who liked a tweet. Returns user rows."""
        ...

    def retweet(self, tweet_id: str) -> dict:
        """Retweet a tweet. Returns engagement response."""
        ...

    def undo_retweet(self, tweet_id: str) -> dict:
        """Remove a retweet. Returns engagement response."""
        ...

    def get_tweet_retweeters(
        self,
        tweet_id: str,
        *,
        max_results: int = 100,
    ) -> list[dict]:
        """Get users who retweeted a tweet. Returns user rows."""
        ...

    def follow_user(self, user_id: str) -> dict:
        """Follow a user. Returns engagement response."""
        ...

    def unfollow_user(self, user_id: str) -> dict:
        """Unfollow a user. Returns engagement response."""
        ...

    def create_quote_tweet(self, quoted_tweet_id: str, text: str) -> CreatedPost:
        """Quote a tweet with new text. Returns created post."""
        ...

    def get_quote_tweets(
        self,
        tweet_id: str,
        *,
        max_results: int = 100,
    ) -> list[dict]:
        """Get quote tweets for a tweet. Returns reference rows."""
        ...

    def search_all_tweets(
        self,
        query: str,
        *,
        max_results: int = 100,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """Full-archive tweet search (requires academic access). Returns reference rows."""
        ...

    def get_post_replies(
        self,
        post_id: str,
        *,
        max_results: int = 50,
    ) -> list[dict]:
        """Fetch replies to a specific post (rows with ``source=conversation``)."""
        ...

    def reply_to_tweet(
        self,
        post_id: str,
        text: str,
    ) -> CreatedPost:
        """Publish a reply to a specific tweet."""
        ...

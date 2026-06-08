"""External reference tweets pulled for post creation (RavenDB collection PulledTweets)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.tweet_media import TweetMediaItem, TweetUrlEntity


class PulledTweetDocument(BaseModel):
    """One X tweet observed during reference compilation, deduped globally by tweet_id."""

    tweet_id: str
    text: str | None = None
    author_id: str | None = None
    created_at: str | None = None
    lang: str | None = None
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    author_followers_count: int | None = None
    text_features: dict = Field(default_factory=dict)
    entity_tags: list[str] = Field(default_factory=list)
    source: str = ""
    trend_query: str | None = None
    duplicate_fetch_count: int = 0
    pull_count: int = 1
    first_pulled_at: str = ""
    last_pulled_at: str = ""
    first_pulled_for_account_id: str = ""
    last_pulled_for_account_id: str = ""
    pulled_for_account_ids: list[str] = Field(default_factory=list)
    last_pulled_slot: str | None = None
    tweet_permalink: str | None = None
    media_types: list[str] = Field(default_factory=list)
    primary_media_type: str | None = None
    media: list[TweetMediaItem] = Field(default_factory=list)
    embed_urls: list[str] = Field(default_factory=list)
    url_entities: list[TweetUrlEntity] = Field(default_factory=list)

    @staticmethod
    def document_id(tweet_id: str) -> str:
        return f"pulledtweets/{tweet_id}"


class PullRecordStats(BaseModel):
    """Summary from one record_pulls batch."""

    new_count: int = 0
    duplicate_count: int = 0
    skipped_no_id: int = 0

"""Tracked X posts per account (RavenDB collection TrackedPosts)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.tweet_media import TweetMediaItem, TweetUrlEntity


class PostCreationMetrics(BaseModel):
    """How a posted tweet was produced (optional on TrackedPosts)."""

    candidates_created: int = 0
    tweets_pulled: int = 0
    tweets_pulled_new: int = 0
    tweets_pulled_duplicates: int = 0
    regeneration_round: int = 0
    chosen_topic: str | None = None
    chosen_topic_id: str | None = None
    source_reference_tweet_id: str | None = None
    chosen_embed_url: str | None = None
    voice_version_hash: str | None = None
    voice_version_seq: int | None = None
    voice_version_label: str | None = None
    source_reference_metrics_at_pick: dict | None = None
    # ── NEW: attribution join (the ONE missing link) ──
    run_id: str | None = None          # joins this post to its PipelineRunDocument (pipelineruns/{run_id})
    pipeline_hash: str | None = None   # the active PipelineSpecDocument.version_hash at post time (doc 04)


class TrackedPostDocument(BaseModel):
    """One posted tweet we poll for engagement."""

    account_id: str
    tweet_id: str
    posted_at: str = ""
    last_fetched_at: str | None = None
    # Set once the tweet is gone from X (404/Tweet not found). Deleted posts keep
    # their last-known metrics for analytics but are never polled again.
    is_deleted: bool = False
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    engagement_rate: float | None = None
    reply_rate: float | None = None
    like_rate: float | None = None
    followers_at_post: int | None = None
    follower_delta: int | None = None
    profile_click_count: int | None = None
    engagement_velocity: float | None = None
    raw_metrics: dict = Field(default_factory=dict)
    creation_metrics: PostCreationMetrics | None = None
    tweet_permalink: str | None = None
    media_types: list[str] = Field(default_factory=list)
    primary_media_type: str | None = None
    media: list[TweetMediaItem] = Field(default_factory=list)
    embed_urls: list[str] = Field(default_factory=list)
    url_entities: list[TweetUrlEntity] = Field(default_factory=list)

    @staticmethod
    def document_id(account_id: str, tweet_id: str) -> str:
        return f"trackedposts/{account_id}-{tweet_id}"

"""Snapshots of tracked post metrics over time."""

from __future__ import annotations

from pydantic import BaseModel


class PostMetricSnapshotDocument(BaseModel):
    account_id: str
    tweet_id: str
    captured_at: str
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    profile_click_count: int | None = None
    engagement_rate: float | None = None
    reply_rate: float | None = None
    like_rate: float | None = None
    engagement_velocity: float | None = None

    @staticmethod
    def document_id(account_id: str, tweet_id: str, captured_at: str) -> str:
        slug = captured_at.replace(":", "").replace(".", "").replace("+", "")
        return f"postmetricsnapshots/{account_id}-{tweet_id}-{slug}"

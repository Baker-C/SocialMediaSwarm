"""
Normalized return types for social operations.

These mirror X/Twitter fields closely for now; when adding LinkedIn etc., map
each vendor response into these DTOs (or extend with optional vendor blocks).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.tweet_media import TweetMediaItem, TweetUrlEntity


class TrendItem(BaseModel):
    name: str
    tweet_volume: int | None = None
    url: str | None = None


class TrendsResult(BaseModel):
    """Result of get_trends (personalized and/or WOEID place trends)."""

    trends: list[TrendItem] = Field(default_factory=list)
    location_name: str | None = None
    woeid: int | None = None
    source: str | None = None  # personalized | woeid | none


class AccountData(BaseModel):
    """Authenticated user or looked-up account (X-shaped)."""

    id: str
    username: str
    name: str | None = None
    description: str | None = None
    followers_count: int | None = None
    following_count: int | None = None
    tweet_count: int | None = None
    listed_count: int | None = None
    created_at: datetime | None = None
    profile_image_url: str | None = None
    verified: bool | None = None
    raw: dict[str, Any] | None = Field(default=None, description="Optional vendor payload for debugging")


class PostData(BaseModel):
    """Single post / tweet with public engagement (X-shaped)."""

    id: str
    text: str | None = None
    author_id: str | None = None
    created_at: datetime | None = None
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    lang: str | None = None
    raw: dict[str, Any] | None = None
    tweet_permalink: str | None = None
    media_types: list[str] = Field(default_factory=list)
    primary_media_type: str | None = None
    media: list[TweetMediaItem] = Field(default_factory=list)
    embed_urls: list[str] = Field(default_factory=list)
    url_entities: list[TweetUrlEntity] = Field(default_factory=list)

    @field_validator("author_id", mode="before")
    @classmethod
    def _coerce_author_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        return s or None


class CreatedPost(BaseModel):
    """Result of create_post."""

    id: str
    text: str | None = None

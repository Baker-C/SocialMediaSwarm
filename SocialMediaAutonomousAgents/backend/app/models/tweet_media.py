"""Shared media and link metadata for tweets (PulledTweets, TrackedPosts, PostData)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TweetMediaItem(BaseModel):
    media_key: str | None = None
    type: str = ""
    url: str | None = None
    preview_image_url: str | None = None


class TweetUrlEntity(BaseModel):
    url: str | None = None
    expanded_url: str | None = None
    display_url: str | None = None


class TweetMediaEnrichment(BaseModel):
    tweet_permalink: str | None = None
    media_types: list[str] = Field(default_factory=list)
    primary_media_type: str | None = None
    media: list[TweetMediaItem] = Field(default_factory=list)
    embed_urls: list[str] = Field(default_factory=list)
    url_entities: list[TweetUrlEntity] = Field(default_factory=list)

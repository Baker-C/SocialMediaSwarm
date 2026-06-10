"""Canonical Pydantic models for pipeline runbook context artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.interval.tweet_topic_preanalysis import GatheredTweet

SourceLabel = Literal["timeline", "own_posts"]


class ArtifactKey(StrEnum):
    ACCOUNT_BUNDLE = "account_bundle"
    TIMELINE_REFERENCES = "timeline_references"
    SEARCH_REFERENCES = "search_references"
    OWN_POSTS = "own_posts"
    TIMELINE_RANKED = "timeline_ranked"
    OWN_POSTS_RANKED = "own_posts_ranked"
    TIMELINE_ANALYSIS = "timeline_analysis"
    OWN_POSTS_ANALYSIS = "own_posts_analysis"


class ReferenceTweetRow(BaseModel):
    """One external reference tweet from X timeline or search."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    tweet_id: str | None = None
    text: str = ""
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    source: str | None = None
    search_query: str | None = None
    matched_queries: list[str] | None = None


class AccountBundle(BaseModel):
    """X profile and tracked-post engagement metrics for one account."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    profile: dict[str, Any] | None = None
    tracked_tweet_ids: list[str] = Field(default_factory=list)
    post_engagements: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TimelineReferencesPayload(BaseModel):
    """External reference pool (timeline + optional search merge metadata)."""

    model_config = ConfigDict(extra="allow")

    timeline_reference_tweets: list[ReferenceTweetRow | dict[str, Any]] = Field(default_factory=list)
    reference_errors: list[str] = Field(default_factory=list)
    search_merged_count: int | None = None
    timeline_only_count: int | None = None
    search_queries_run: list[str] | None = None
    pulled_tweet_stats: dict[str, Any] | None = None


class SearchReferencesPayload(BaseModel):
    """Reference tweets from X recent-search queries."""

    model_config = ConfigDict(extra="allow")

    search_reference_tweets: list[ReferenceTweetRow | dict[str, Any]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    per_query_counts: dict[str, int] = Field(default_factory=dict)
    reference_errors: list[str] = Field(default_factory=list)
    pulled_tweet_stats: dict[str, Any] | None = None


class OwnPostsPayload(BaseModel):
    """Own-post history with engagement metrics from RavenDB."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    tweet_ids: list[str] = Field(default_factory=list)
    posts: list[dict[str, Any]] = Field(default_factory=list)


class RankedReferencesPayload(BaseModel):
    """Top-N ranked reference rows and selected winner."""

    model_config = ConfigDict(extra="allow")

    ranked: list[GatheredTweet | dict[str, Any]] = Field(default_factory=list)
    winner: GatheredTweet | dict[str, Any] | None = None


class ReferencePatternBrief(BaseModel):
    """LLM or deterministic pattern summary for compose context."""

    model_config = ConfigDict(extra="allow")

    source: SourceLabel | str = ""
    post_count: int = 0
    features: dict[str, Any] = Field(default_factory=dict)
    pattern_summary: str = ""
    winning_topics: list[str] = Field(default_factory=list)
    voice_signals: list[str] = Field(default_factory=list)
    recommended_constraints: list[str] = Field(default_factory=list)
    skipped: bool | None = None
    skip_reason: str | None = None
    errors: list[str] | None = None
    selected_winner_id: str | None = None


@dataclass(frozen=True)
class ArtifactDef:
    key: ArtifactKey
    model: type[BaseModel]
    purpose: str
    producer: str = ""


ARTIFACTS: dict[ArtifactKey, ArtifactDef] = {
    ArtifactKey.ACCOUNT_BUNDLE: ArtifactDef(
        ArtifactKey.ACCOUNT_BUNDLE,
        AccountBundle,
        "X profile and tracked-post engagement metrics",
        "steps.load_account_bundle",
    ),
    ArtifactKey.TIMELINE_REFERENCES: ArtifactDef(
        ArtifactKey.TIMELINE_REFERENCES,
        TimelineReferencesPayload,
        "External reference tweet pool for ranking",
        "steps.fetch_timeline_references / steps.merge_external_references",
    ),
    ArtifactKey.SEARCH_REFERENCES: ArtifactDef(
        ArtifactKey.SEARCH_REFERENCES,
        SearchReferencesPayload,
        "Search-sourced reference tweet pool",
        "steps.fetch_search_references",
    ),
    ArtifactKey.OWN_POSTS: ArtifactDef(
        ArtifactKey.OWN_POSTS,
        OwnPostsPayload,
        "Own-post history with engagement metrics",
        "steps.fetch_own_post_history",
    ),
    ArtifactKey.TIMELINE_RANKED: ArtifactDef(
        ArtifactKey.TIMELINE_RANKED,
        RankedReferencesPayload,
        "Top external references ranked by engagement",
        "steps.rank_external_references",
    ),
    ArtifactKey.OWN_POSTS_RANKED: ArtifactDef(
        ArtifactKey.OWN_POSTS_RANKED,
        RankedReferencesPayload,
        "Top own posts ranked by engagement",
        "steps.rank_own_posts",
    ),
    ArtifactKey.TIMELINE_ANALYSIS: ArtifactDef(
        ArtifactKey.TIMELINE_ANALYSIS,
        ReferencePatternBrief,
        "External reference pattern brief for compose",
        "steps.brief_external_references",
    ),
    ArtifactKey.OWN_POSTS_ANALYSIS: ArtifactDef(
        ArtifactKey.OWN_POSTS_ANALYSIS,
        ReferencePatternBrief,
        "Own-post voice and success pattern brief",
        "steps.brief_own_posts",
    ),
}


ARTIFACT_KEY_BY_CTX_KEY: dict[str, ArtifactKey] = {k.value: k for k in ArtifactKey}


def artifact_key_for_ctx_key(ctx_key: str) -> ArtifactKey | None:
    return ARTIFACT_KEY_BY_CTX_KEY.get(ctx_key)

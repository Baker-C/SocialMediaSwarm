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
    # ACT tail artifacts (doc 06)
    COMPOSED_POST = "composed_post"
    SAFETY_VERDICT = "safety_verdict"
    PUBLISHED_POST = "published_post"
    # Reply pipeline artifacts (doc 12)
    MENTIONS = "mentions"
    MENTIONS_RANKED = "mentions_ranked"
    REPLY_DRAFT = "reply_draft"
    REPLY_VERDICT = "reply_verdict"
    REPLY_RESULT = "reply_result"


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


# ── ACT tail artifacts (doc 06) ──


class ComposedPost(BaseModel):
    """The selected post body and the provenance of the compose loop that produced it.

    This is the SERIALIZABLE view. The live winner GatheredTweet and the resolved
    chosen_embed_url object travel via deps.live (not here) so we never force a
    non-serializable through model_dump.
    """

    model_config = ConfigDict(extra="allow")

    body: str
    # Outer-loop bookkeeping (mirrors runner.py:304-365 today)
    reference_index: int = 0          # which ranked ref won (0-based)
    references_tried: int = 0
    regeneration_round: int = 0       # inner-loop round of the accepted body
    source_reference_tweet_id: str | None = None
    chosen_embed_url: str | None = None
    # Source-pick metrics snapshot (mirrors runner.py:402-411)
    source_reference_metrics_at_pick: dict[str, Any] | None = None
    # Compose-cost bookkeeping for the creation metrics
    tweets_pulled: int = 0
    tweets_pulled_new: int = 0
    tweets_pulled_duplicates: int = 0


class SafetyVerdict(BaseModel):
    """Final guardian outcome of the compose loop.

    approved=True  → a body passed guardian.evaluate(); compose_until_safe wrote COMPOSED_POST.
    approved=False → every reference/round was rejected; last_reject is the terminal reason
                     and COMPOSED_POST is absent. publish_post will skip.
    """

    approved: bool
    last_reject: str | None = None
    references_tried: int = 0          # the rejected legacy return needs this (runner.py:373)
    regeneration_round: int = 0        # round of the accepted body (0 when rejected)


class PublishedPost(BaseModel):
    """Result of the X publish + finalize. Carries the FULL finalize_post() dict under
    `result` so the runner can reconstruct the exact legacy return shape (including the
    full `tweet` object), plus flat convenience fields for the trace/dashboard."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    posted: bool = False
    tweet_id: str | None = None
    skipped_reason: str | None = None          # set when SAFETY_VERDICT.approved is False
    regeneration_round: int | None = None
    idempotency_key: str | None = None          # see §5.2
    note: str | None = None
    # The COMPLETE finalize_post(...) return dict ({account_id, tweet, regeneration_round,
    # note?, creation_metrics?}) — verbatim, untruncated. The runner's _result_from_run (07)
    # returns THIS as the legacy result so `'tweet' in out` and the full tweet object survive.
    result: dict[str, Any] = Field(default_factory=dict)


# ── Reply pipeline artifacts (doc 12) ──


class MentionsPayload(BaseModel):
    """Recent mentions of the account for reply candidacy."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    mentions: list[dict[str, Any]] = Field(default_factory=list)  # tweet-row dicts (rankable)


class ReplyDraft(BaseModel):
    """Composed reply body + target mention."""

    model_config = ConfigDict(extra="allow")

    body: str
    in_reply_to_tweet_id: str
    target_author_handle: str | None = None
    regeneration_round: int = 0


class ReplyVerdict(BaseModel):
    """Reply|skip decision + guardian outcome."""

    decision: Literal["reply", "skip"]
    approved: bool = False
    in_reply_to_tweet_id: str | None = None
    reason: str | None = None


class ReplyResult(BaseModel):
    """X reply publish + finalize result."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    posted: bool = False
    skipped_reason: str | None = None
    note: str | None = None


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
    ArtifactKey.COMPOSED_POST: ArtifactDef(
        ArtifactKey.COMPOSED_POST,
        ComposedPost,
        "Selected post body + compose-loop provenance",
        "steps.compose_step",
    ),
    ArtifactKey.SAFETY_VERDICT: ArtifactDef(
        ArtifactKey.SAFETY_VERDICT,
        SafetyVerdict,
        "Final guardian verdict of the compose loop",
        "steps.compose_step",
    ),
    ArtifactKey.PUBLISHED_POST: ArtifactDef(
        ArtifactKey.PUBLISHED_POST,
        PublishedPost,
        "X publish + finalize result",
        "steps.publish_step",
    ),
    # Reply pipeline (doc 12)
    ArtifactKey.MENTIONS: ArtifactDef(
        ArtifactKey.MENTIONS,
        MentionsPayload,
        "Recent mentions of the account for reply candidacy",
        "steps.fetch_mentions",
    ),
    ArtifactKey.MENTIONS_RANKED: ArtifactDef(
        ArtifactKey.MENTIONS_RANKED,
        RankedReferencesPayload,
        "Top mentions ranked by engagement",
        "steps.rank_mentions",
    ),
    ArtifactKey.REPLY_DRAFT: ArtifactDef(
        ArtifactKey.REPLY_DRAFT,
        ReplyDraft,
        "Composed reply body + target mention",
        "steps.reply_compose_step",
    ),
    ArtifactKey.REPLY_VERDICT: ArtifactDef(
        ArtifactKey.REPLY_VERDICT,
        ReplyVerdict,
        "Reply|skip decision + guardian outcome",
        "steps.reply_compose_step",
    ),
    ArtifactKey.REPLY_RESULT: ArtifactDef(
        ArtifactKey.REPLY_RESULT,
        ReplyResult,
        "X reply publish + finalize result",
        "steps.reply_publish_step",
    ),
}


ARTIFACT_KEY_BY_CTX_KEY: dict[str, ArtifactKey] = {k.value: k for k in ArtifactKey}


def artifact_key_for_ctx_key(ctx_key: str) -> ArtifactKey | None:
    return ARTIFACT_KEY_BY_CTX_KEY.get(ctx_key)

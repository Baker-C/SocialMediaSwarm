"""Timeline reference selection for posting (single path)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.social.tweet_enrichment import select_chosen_post_media_url

logger = logging.getLogger(__name__)

# Weighted popularity for timeline reference ranking (quote_count excluded).
_WEIGHT_LIKE = 0.7
_WEIGHT_REPLY = 0.6
_WEIGHT_RETWEET = 1.0
_WEIGHT_IMPRESSION = 0.1


class GatheredTweet(BaseModel):
    tweet_id: str
    text: str
    popularity_score: float
    metrics: dict[str, Any] = Field(default_factory=dict)


class TweetTopicPreanalysis(BaseModel):
    skipped: bool = False
    skip_reason: str | None = None
    selected_tweet_ids: list[str] = Field(default_factory=list)
    chosen_embed_url: str | None = None
    filtered_post_engagements: list[dict[str, Any]] = Field(default_factory=list)
    source_label: str | None = None


def _metric_count(metrics: dict[str, Any], key: str) -> float:
    val = metrics.get(key)
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    return 0.0


def popularity_score(metrics: dict[str, Any]) -> float:
    """
    Weighted engagement score for ranking timeline references.

    likes × 0.7, replies × 0.6, retweets × 1.0, impressions × 0.1.
    Quote tweets are not included.
    """
    return (
        _WEIGHT_LIKE * _metric_count(metrics, "like_count")
        + _WEIGHT_REPLY * _metric_count(metrics, "reply_count")
        + _WEIGHT_RETWEET * _metric_count(metrics, "retweet_count")
        + _WEIGHT_IMPRESSION * _metric_count(metrics, "impression_count")
    )


def parse_engagement_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[GatheredTweet], dict[str, dict[str, Any]]]:
    """Split rows with usable text vs all rows by tweet id."""
    text_tweets: list[GatheredTweet] = []
    all_by_id: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("error"):
            continue
        tid = str(row.get("id") or row.get("tweet_id") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        all_by_id[tid] = row
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        text_tweets.append(
            GatheredTweet(
                tweet_id=tid,
                text=text,
                popularity_score=popularity_score(row),
                metrics=row,
            )
        )
    return text_tweets, all_by_id


def rank_timeline_references(
    rows: list[dict[str, Any]],
    *,
    exclude_ids: frozenset[str] | None = None,
    also_exclude: frozenset[str] | None = None,
) -> list[GatheredTweet]:
    """All URL-pool tweets with text, highest popularity first, minus excluded ids."""
    text_tweets, _ = parse_engagement_rows(rows)
    excluded = frozenset(exclude_ids or frozenset()) | frozenset(also_exclude or frozenset())
    candidates = [t for t in text_tweets if t.tweet_id not in excluded]
    return sorted(candidates, key=lambda t: t.popularity_score, reverse=True)


def select_top_timeline_reference(
    rows: list[dict[str, Any]],
    *,
    exclude_ids: frozenset[str] | None = None,
) -> GatheredTweet | None:
    """Pick the highest popularity-score timeline tweet not in ``exclude_ids``."""
    ranked = rank_timeline_references(rows, exclude_ids=exclude_ids)
    return ranked[0] if ranked else None


def preanalysis_from_winner(winner: GatheredTweet) -> TweetTopicPreanalysis:
    """Build preanalysis payload for a single chosen reference tweet."""
    embed_url = select_chosen_post_media_url(winner.metrics)
    return TweetTopicPreanalysis(
        skipped=False,
        selected_tweet_ids=[winner.tweet_id],
        chosen_embed_url=embed_url,
        filtered_post_engagements=[dict(winner.metrics)],
        source_label=str(winner.metrics.get("source") or "following_timeline"),
    )


def reference_pool_skip_reason(
    rows: list[dict[str, Any]],
    *,
    exclude_ids: frozenset[str] | None = None,
) -> str | None:
    """Return skip_reason when ``rank_timeline_references`` would be empty."""
    text_tweets, _ = parse_engagement_rows(rows)
    if not text_tweets:
        return "no_reference_with_urls"
    excluded = exclude_ids or frozenset()
    if excluded and not rank_timeline_references(rows, exclude_ids=excluded):
        return "all_references_already_copied"
    return None


def reference_winner_from_pool(
    rows: list[dict[str, Any]],
    preanalysis: TweetTopicPreanalysis,
) -> GatheredTweet | None:
    """Resolve the chosen reference row from preanalysis output."""
    if preanalysis.skipped or not preanalysis.selected_tweet_ids:
        return None
    target = preanalysis.selected_tweet_ids[0]
    text_tweets, _ = parse_engagement_rows(rows)
    for tweet in text_tweets:
        if tweet.tweet_id == target:
            return tweet
    return None


def run_reference_preanalysis(
    reference_tweets: list[dict[str, Any]],
    *,
    niche: str,
    exclude_ids: frozenset[str] | None = None,
) -> TweetTopicPreanalysis:
    """Select top unused URL-bearing timeline reference (rows should already be URL-filtered)."""
    _ = niche  # reserved for future compose context
    excluded = exclude_ids or frozenset()
    skip = reference_pool_skip_reason(reference_tweets, exclude_ids=excluded)
    if skip:
        logger.info("reference_preanalysis: skipped — %s", skip)
        return TweetTopicPreanalysis(skipped=True, skip_reason=skip, filtered_post_engagements=[])

    winner = select_top_timeline_reference(reference_tweets, exclude_ids=excluded)
    assert winner is not None
    logger.info(
        "reference_preanalysis: selected timeline tweet_id=%s score=%s excluded=%d",
        winner.tweet_id,
        winner.popularity_score,
        len(excluded),
    )
    return preanalysis_from_winner(winner)


def apply_preanalysis_to_account_bundle(
    bundle_account: dict[str, Any],
    preanalysis: TweetTopicPreanalysis,
) -> dict[str, Any]:
    """Attach reference engagements for trace; generation uses compose step directly."""
    updated = dict(bundle_account)
    updated["topic_preanalysis"] = preanalysis.model_dump()
    if preanalysis.skipped:
        updated["reference_engagements"] = []
    else:
        updated["reference_engagements"] = preanalysis.filtered_post_engagements
    return updated

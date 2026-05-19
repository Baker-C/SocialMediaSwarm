"""Timeline reference selection for posting (single path)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.social.tweet_enrichment import select_chosen_post_media_url

logger = logging.getLogger(__name__)


class GatheredTweet(BaseModel):
    tweet_id: str
    text: str
    interaction_score: int
    metrics: dict[str, Any] = Field(default_factory=dict)


class TweetTopicPreanalysis(BaseModel):
    skipped: bool = False
    skip_reason: str | None = None
    selected_tweet_ids: list[str] = Field(default_factory=list)
    chosen_embed_url: str | None = None
    filtered_post_engagements: list[dict[str, Any]] = Field(default_factory=list)
    source_label: str | None = None


def interaction_score(metrics: dict[str, Any]) -> int:
    """Sum engagement counts (not impressions)."""
    total = 0
    for key in ("like_count", "reply_count", "retweet_count", "quote_count"):
        val = metrics.get(key)
        if isinstance(val, int) and val > 0:
            total += val
    return total


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
                interaction_score=interaction_score(row),
                metrics=row,
            )
        )
    return text_tweets, all_by_id


def select_top_timeline_reference(rows: list[dict[str, Any]]) -> GatheredTweet | None:
    """Pick the timeline tweet with the highest engagement score."""
    text_tweets, _ = parse_engagement_rows(rows)
    if not text_tweets:
        return None
    return max(text_tweets, key=lambda t: t.interaction_score)


def run_reference_preanalysis(
    reference_tweets: list[dict[str, Any]],
    *,
    niche: str,
) -> TweetTopicPreanalysis:
    """Select top URL-bearing timeline reference (rows should already be URL-filtered)."""
    _ = niche  # reserved for future compose context
    winner = select_top_timeline_reference(reference_tweets)
    if winner is None:
        logger.info(
            "reference_preanalysis: skipped — no timeline tweets with text in pool of %d",
            len(reference_tweets),
        )
        return TweetTopicPreanalysis(
            skipped=True,
            skip_reason="no_reference_with_urls",
            filtered_post_engagements=[],
        )

    embed_url = select_chosen_post_media_url(winner.metrics)
    logger.info(
        "reference_preanalysis: selected timeline tweet_id=%s score=%s",
        winner.tweet_id,
        winner.interaction_score,
    )
    return TweetTopicPreanalysis(
        skipped=False,
        selected_tweet_ids=[winner.tweet_id],
        chosen_embed_url=embed_url,
        filtered_post_engagements=[dict(winner.metrics)],
        source_label=str(winner.metrics.get("source") or "following_timeline"),
    )


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

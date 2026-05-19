"""Normalize PostData / Tweepy tweets into tick bundle reference rows."""

from __future__ import annotations

from typing import Any

from app.models.tweet_media import TweetMediaEnrichment
from app.social.dtos import PostData
from app.social.tweet_enrichment import enrichment_to_row_dict


def post_data_to_reference_row(post: PostData, *, source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": post.id,
        "tweet_id": post.id,
        "text": post.text,
        "author_id": post.author_id,
        "like_count": post.like_count,
        "reply_count": post.reply_count,
        "retweet_count": post.retweet_count,
        "quote_count": post.quote_count,
        "impression_count": post.impression_count,
        "lang": post.lang,
        "source": source,
    }
    if post.created_at is not None:
        row["created_at"] = post.created_at.isoformat()
    if post.tweet_permalink or post.media_types or post.embed_urls:
        row.update(
            enrichment_to_row_dict(
                TweetMediaEnrichment(
                    tweet_permalink=post.tweet_permalink,
                    media_types=list(post.media_types),
                    primary_media_type=post.primary_media_type,
                    media=list(post.media),
                    embed_urls=list(post.embed_urls),
                    url_entities=list(post.url_entities),
                )
            )
        )
    if extra:
        row.update(extra)
    return row


def filter_out_own_tweets(rows: list[dict[str, Any]], authenticated_user_id: str | None) -> list[dict[str, Any]]:
    if not authenticated_user_id:
        return rows
    own = str(authenticated_user_id).strip()
    if not own:
        return rows
    return [r for r in rows if str(r.get("author_id") or "").strip() != own]

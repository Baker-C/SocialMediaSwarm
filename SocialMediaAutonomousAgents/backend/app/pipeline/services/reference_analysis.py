"""Shared helpers for reference rank and pattern-brief steps."""

from __future__ import annotations

from typing import Any

from app.metrics.derived import extract_entities, extract_text_features


def enrich_row_features(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["text_features"] = extract_text_features(str(out.get("text") or ""))
    out["entity_tags"] = extract_entities(out)
    return out


def top_entities(rows: list[dict[str, Any]], limit: int = 12) -> list[str]:
    tags: list[str] = []
    for r in rows:
        for t in r.get("entity_tags") or []:
            if isinstance(t, str) and t.strip():
                tags.append(t.strip())
    seen: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen[:limit]


def avg_char_count(rows: list[dict[str, Any]]) -> float | None:
    counts = []
    for r in rows:
        tf = r.get("text_features")
        if isinstance(tf, dict):
            cc = tf.get("char_count")
            if isinstance(cc, int):
                counts.append(cc)
    if not counts:
        return None
    return float(sum(counts)) / float(len(counts))


def rows_from_tracked(posts: list[Any]) -> list[dict[str, Any]]:
    """Normalize TrackedPost documents into reference-rank rows."""
    rows: list[dict[str, Any]] = []
    for doc in posts:
        if not isinstance(doc, dict):
            continue
        text = str(doc.get("post_text") or doc.get("text") or "").strip()
        raw = doc.get("raw_metrics") if isinstance(doc.get("raw_metrics"), dict) else {}
        row = {
            "tweet_id": doc.get("tweet_id"),
            "id": doc.get("tweet_id"),
            "text": text or str(raw.get("text") or ""),
            "like_count": doc.get("like_count") if doc.get("like_count") is not None else raw.get("like_count"),
            "reply_count": doc.get("reply_count") if doc.get("reply_count") is not None else raw.get("reply_count"),
            "retweet_count": doc.get("retweet_count")
            if doc.get("retweet_count") is not None
            else raw.get("retweet_count"),
            "quote_count": doc.get("quote_count") if doc.get("quote_count") is not None else raw.get("quote_count"),
            "impression_count": doc.get("impression_count")
            if doc.get("impression_count") is not None
            else raw.get("impression_count"),
            "posted_at": doc.get("posted_at"),
            "source": "own_posts",
        }
        if row.get("tweet_id"):
            rows.append(row)
    return rows


def authenticated_user_id_from_bundle(bundle: dict[str, Any]) -> str | None:
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    if isinstance(prof, dict) and prof.get("id") is not None:
        return str(prof["id"])
    return None

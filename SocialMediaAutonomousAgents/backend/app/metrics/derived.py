"""Pure metric derivations used by jobs and repositories."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.interval.tweet_topic_preanalysis import popularity_score

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
_MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")
_URL_RE = re.compile(r"https?://\S+")


def compute_rates(metrics: dict[str, Any]) -> dict[str, float | None]:
    """Compute optional rates; returns ``None`` values when impressions missing."""
    impressions = metrics.get("impression_count")
    if not isinstance(impressions, (int, float)) or impressions <= 0:
        return {
            "engagement_rate": None,
            "reply_rate": None,
            "like_rate": None,
        }
    impressions_f = float(impressions)
    like = _num(metrics.get("like_count"))
    reply = _num(metrics.get("reply_count"))
    retweet = _num(metrics.get("retweet_count"))
    quote = _num(metrics.get("quote_count"))
    total = like + reply + retweet + quote
    return {
        "engagement_rate": total / impressions_f,
        "reply_rate": reply / impressions_f,
        "like_rate": like / impressions_f,
    }


def compute_velocity(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> float | None:
    """Simple engagement velocity across two snapshots."""
    if not previous or not current:
        return None
    prev_eng = _engagement_total(previous)
    curr_eng = _engagement_total(current)
    prev_imp = _num(previous.get("impression_count"))
    curr_imp = _num(current.get("impression_count"))
    d_imp = curr_imp - prev_imp
    if d_imp <= 0:
        return None
    d_eng = curr_eng - prev_eng
    return d_eng / float(d_imp)


def normalized_reference_score(metrics: dict[str, Any], author_followers: int | None) -> float:
    """Follower-normalized ranking score with deterministic fallback."""
    base = float(popularity_score(metrics))
    if not isinstance(author_followers, int) or author_followers <= 0:
        return base
    scale = max(1.0, float(author_followers) ** 0.5)
    return base / scale


def extract_text_features(text: str | None) -> dict[str, Any]:
    body = (text or "").strip()
    words = _WORD_RE.findall(body)
    hashtags = _HASHTAG_RE.findall(body)
    mentions = _MENTION_RE.findall(body)
    return {
        "char_count": len(body),
        "word_count": len(words),
        "hashtag_count": len(hashtags),
        "mention_count": len(mentions),
        "url_count": len(_URL_RE.findall(body)),
        "question_count": body.count("?"),
        "exclamation_count": body.count("!"),
        "is_all_caps": body.isupper() if body else False,
    }


def extract_entities(row: dict[str, Any]) -> list[str]:
    text = str(row.get("text") or "")
    entities = row.get("entities") if isinstance(row.get("entities"), dict) else {}
    tags: list[str] = []
    for h in entities.get("hashtags") or []:
        if isinstance(h, dict) and h.get("tag"):
            tags.append(str(h["tag"]).lower())
    for m in entities.get("mentions") or []:
        if isinstance(m, dict) and m.get("username"):
            tags.append(f"@{str(m['username']).lower()}")
    for token in _HASHTAG_RE.findall(text):
        tags.append(str(token).lower())
    for token in _MENTION_RE.findall(text):
        tags.append(f"@{str(token).lower()}")
    normalized = [t.strip() for t in tags if str(t).strip()]
    if not normalized:
        return []
    most_common = Counter(normalized).most_common(20)
    return [k for k, _ in most_common]


def _num(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _engagement_total(metrics: dict[str, Any]) -> float:
    return _num(metrics.get("like_count")) + _num(metrics.get("reply_count")) + _num(
        metrics.get("retweet_count")
    ) + _num(metrics.get("quote_count"))

"""Build X API search queries and shared trend keyword helpers."""

from __future__ import annotations

import re


def trend_keywords(trend_name: str) -> list[str]:
    """Tokenize a trend name for loose text matching."""
    cleaned = re.sub(r"^#+", "", (trend_name or "").strip().lower())
    if not cleaned:
        return []
    parts = re.split(r"[\s\-_/]+", cleaned)
    return [p for p in parts if len(p) > 2]


def trend_slug(trend_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (trend_name or "").lower()).strip("-")
    return slug[:48] or "trend"


def build_search_query(trend_name: str) -> str:
    """
    Build a recent-search query for a trend label.

    Appends ``-is:retweet lang:en`` to reduce noise.
    """
    name = (trend_name or "").strip()
    if not name:
        return ""
    if name.startswith("#"):
        core = name.split()[0]
        base = core if core.startswith("#") else f"#{core.lstrip('#')}"
    elif " " in name or "-" in name:
        escaped = name.replace('"', "")
        base = f'"{escaped}"'
    else:
        base = name
    return f"{base} -is:retweet lang:en"


_TREND_STOPWORDS = frozenset(
    {
        "and", "the", "for", "with", "from", "into", "out", "over", "amid", "now",
        "new", "gets", "has", "its", "one", "thing", "tops", "asks", "says", "after",
    }
)


def trend_topic_query(trend_name: str, *, max_terms: int = 3) -> str:
    """Reduce a trend headline to a short keyword query (the salient terms).

    X recent-search treats a quoted multi-word phrase as an exact match, so a full
    trend headline matches almost nothing. The top content keywords (stopwords
    dropped) co-occur in the live discussion and surface plenty of references.
    """
    kws = [k for k in trend_keywords(trend_name) if k not in _TREND_STOPWORDS]
    return " ".join(kws[:max_terms])


def tweet_matches_trend(text: str, trend_name: str) -> bool:
    """True if any trend keyword appears in tweet text."""
    keywords = trend_keywords(trend_name)
    if not keywords:
        return True
    text_l = (text or "").lower()
    return any(k in text_l for k in keywords)

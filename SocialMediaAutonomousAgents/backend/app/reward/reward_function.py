"""Normalized per-post reward for the Interpreter MEASURE phase.

Pure functions over already-polled metric rows. NO X-API calls, NO I/O.
Consumes the reach-normalized engagement_rate and engagement_velocity that the
engagement jobs already compute and store (see app/metrics/derived.py).

reward in [0, 1]; None means "insufficient data" (exclude from averages),
NOT "bad post" (which is a real, low, non-None reward).
"""

from __future__ import annotations

from typing import Any

from app.metrics.derived import compute_rates

# --- Tunable defaults (chosen, not fit; one account, few posts) ---
ENG_RATE_REFERENCE = 0.05   # engagement rate that maps to R=0.5 ("good" X post)
W_ENGAGEMENT = 0.60
W_VELOCITY = 0.25
W_REPLY = 0.15


def _num(value: Any) -> float:
    """Coerce numeric value, excluding booleans (which are int subclass)."""
    if isinstance(value, bool):           # bool is an int subclass; exclude
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _saturate(x: float, ref: float) -> float:
    """Monotonic, bounded squash: 0->0, ref->0.5, inf->1. ref must be > 0."""
    if x <= 0:
        return 0.0
    return x / (x + ref)


def _engagement_rate(row: dict[str, Any]) -> float | None:
    """Stored rate if present, else recompute deterministically from counts."""
    rate = row.get("engagement_rate")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        return float(rate)
    return compute_rates(row).get("engagement_rate")  # None if impressions <= 0


def post_reward(row: dict[str, Any]) -> float | None:
    """Normalized reward in [0, 1], or None if there is not enough data.

    Insufficient data == no measured reach (impression_count missing or 0).
    Everything else yields a real number, including a legitimate ~0 for a
    post that reached people but earned no engagement.
    """
    impressions = row.get("impression_count")
    if not isinstance(impressions, (int, float)) or isinstance(impressions, bool):
        return None
    if impressions <= 0:
        return None

    e = _engagement_rate(row)
    if e is None:                          # impressions guard already passed, but be safe
        return None
    r_eng = _saturate(e, ENG_RATE_REFERENCE)

    likes = _num(row.get("like_count"))
    replies = _num(row.get("reply_count"))
    retweets = _num(row.get("retweet_count"))
    quotes = _num(row.get("quote_count"))
    total_eng = likes + replies + retweets + quotes
    r_reply = (replies / total_eng) if total_eng > 0 else 0.0

    vel = row.get("engagement_velocity")
    if isinstance(vel, (int, float)) and not isinstance(vel, bool):
        r_vel = _saturate(float(vel), ENG_RATE_REFERENCE)
        return W_ENGAGEMENT * r_eng + W_VELOCITY * r_vel + W_REPLY * r_reply

    # Velocity absent (common for fresh posts): drop its term, renormalize.
    denom = W_ENGAGEMENT + W_REPLY
    return (W_ENGAGEMENT / denom) * r_eng + (W_REPLY / denom) * r_reply


def account_avg_reward(rows: list[dict[str, Any]]) -> float | None:
    """Mean of per-post rewards, excluding posts with insufficient data (None).

    Returns None if no post qualifies — LEARN must read None as
    'no signal; do not promote or demote', never as 0.
    """
    scored = [r for r in (post_reward(row) for row in rows) if r is not None]
    if not scored:
        return None
    return sum(scored) / len(scored)

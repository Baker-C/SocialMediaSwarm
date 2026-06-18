"""Attribution-join projection: one row per posted tweet, linking a run + pipeline
version to the reward it ultimately earned. Plain last-writer-wins document — NOT
event-sourced. Stamped at publish, updated in place as engagement metrics arrive."""

from __future__ import annotations

from pydantic import BaseModel, Field


def compute_reward(metrics: dict | None) -> float | None:
    """Single scalar an evaluator optimizes. Engagement-rate first (impression-normalized,
    fairest across posts of different reach); falls back to None until impressions exist.

    `metrics` is the same dict the engagement jobs already build (it has been through
    compute_rates(), so engagement_rate/reply_rate/like_rate are present when impressions>0).
    We do NOT recompute rates here — we read what the job computed."""
    if not metrics:
        return None
    rate = metrics.get("engagement_rate")
    if isinstance(rate, (int, float)):
        return float(rate)
    return None


class OutcomeLedgerDocument(BaseModel):
    """One posted tweet's attribution row. Document id: outcomeledger/{account_id}-{post_id}."""

    run_id: str | None = None            # join → pipelineruns/{run_id} (may be None for legacy/force edge)
    account_id: str
    post_id: str                         # the X tweet id (== TrackedPostDocument.tweet_id)
    soul_hash: str | None = None         # account.voice_version_hash at post time
    pipeline_hash: str | None = None     # active PipelineSpecDocument.version_hash at post time (doc 04)
    reward: float | None = None          # compute_reward(raw_metrics); None until impressions land
    raw_metrics: dict = Field(default_factory=dict)  # last-seen engagement dict (snapshot, untruncated)
    recorded_at: str = ""                # ISO of the last write (publish, then each refresh)

    @staticmethod
    def document_id(account_id: str, post_id: str) -> str:
        return f"outcomeledger/{account_id}-{post_id}"

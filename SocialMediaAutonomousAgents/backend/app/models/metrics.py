"""Aggregated account metrics documents."""

from __future__ import annotations

from pydantic import BaseModel


class AccountMetricsDocument(BaseModel):
    account_id: str
    computed_at: str
    avg_engagement_rate: float | None = None
    avg_reply_rate: float | None = None
    avg_like_rate: float | None = None
    avg_follower_delta: float | None = None
    positive_delta_avg_engagement: float | None = None
    non_positive_delta_avg_engagement: float | None = None
    follower_delta_engagement_gap: float | None = None

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"accountmetrics/{account_id}"

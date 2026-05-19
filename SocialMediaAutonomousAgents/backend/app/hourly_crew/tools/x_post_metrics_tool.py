"""CrewAI tool: metrics for a single tracked post."""

from __future__ import annotations

import json
from typing import Any

from app.services.twitter_service import TwitterService


def fetch_post_metrics(twitter: TwitterService, account_id: str, tweet_id: str) -> str:
    metrics = twitter.get_tweet_metrics(account_id, tweet_id)
    return json.dumps(metrics, default=str)


def make_x_post_metrics_tool(twitter: TwitterService) -> Any:
    try:
        from crewai.tools import tool
    except ImportError:
        return None

    @tool("fetch_x_post_metrics")
    def _tool(account_id: str, tweet_id: str) -> str:
        """Fetch engagement metrics for one X post."""
        return fetch_post_metrics(twitter, account_id, tweet_id)

    return _tool

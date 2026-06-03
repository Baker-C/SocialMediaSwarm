"""CrewAI tool: list tracked post IDs for an account."""

from __future__ import annotations

import json
from typing import Any

from app.services.post_registry import TrackedPostRepository


def list_tracked_ids(post_registry: TrackedPostRepository | None, account_id: str) -> list[str]:
    if post_registry is None:
        return []
    return post_registry.list_tweet_ids(account_id)


def make_tracked_posts_tool(post_registry: TrackedPostRepository | None) -> Any:
    try:
        from crewai.tools import tool
    except ImportError:
        return None

    @tool("list_tracked_post_ids")
    def _tool(account_id: str) -> str:
        """List tweet IDs tracked for engagement polling."""
        return json.dumps(list_tracked_ids(post_registry, account_id))

    return _tool

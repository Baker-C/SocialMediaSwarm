"""fetch_search_references runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core.config import settings
from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext


def test_fetch_search_references_skipped_when_disabled() -> None:
    ctx = TickRunContext(account_id="acct", slot="s1")
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock(), post_registry=MagicMock())
    original = settings.trend_tweet_search_enabled
    try:
        settings.trend_tweet_search_enabled = False
        result = steps.fetch_search_references(ctx, deps)
    finally:
        settings.trend_tweet_search_enabled = original
    assert result.skipped and result.skip_reason == "search_disabled"


def test_fetch_search_references_skipped_when_no_queries() -> None:
    ctx = TickRunContext(account_id="acct", slot="s1")
    repo = MagicMock()
    acc = MagicMock()
    acc.search_queries = []
    repo.load.return_value = acc
    deps = PostRunDeps(tick_data=MagicMock(), repo=repo, post_registry=MagicMock())
    original = settings.trend_tweet_search_enabled
    try:
        settings.trend_tweet_search_enabled = True
        result = steps.fetch_search_references(ctx, deps)
    finally:
        settings.trend_tweet_search_enabled = original
    assert result.skipped and result.skip_reason == "no_search_queries"

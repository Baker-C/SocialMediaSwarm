"""search_pool runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.account import AccountDocument
from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext


def test_search_pool_skipped_when_disabled() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock())
    with patch("app.pipeline.services.steps.settings") as mock_settings:
        mock_settings.trend_tweet_search_enabled = False
        result = steps.search_pool(ctx, deps)
    assert result.skipped
    assert result.skip_reason == "search_disabled"


def test_search_pool_skipped_when_no_queries() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    repo = MagicMock()
    repo.load.return_value = AccountDocument(account_id="a1", niche="News")
    deps = PostRunDeps(tick_data=MagicMock(), repo=repo)
    with patch("app.pipeline.services.steps.settings") as mock_settings:
        mock_settings.trend_tweet_search_enabled = True
        result = steps.search_pool(ctx, deps)
    assert result.skipped
    assert result.skip_reason == "no_search_queries"

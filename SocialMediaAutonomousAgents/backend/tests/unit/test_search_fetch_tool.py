"""data.search_fetch pipeline tool tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.pipeline.tools.data import search_fetch
from app.pipeline.types.context import TickRunContext


def test_search_fetch_tool_sets_context() -> None:
    tick_data = MagicMock()
    tick_data.compile_search_reference_tweets.return_value = {
        "search_reference_tweets": [{"id": "1"}],
        "search_queries": ["news lang:en"],
    }
    ctx = TickRunContext(account_id="acct1", slot="2026-06-08-10", niche="News")

    result = search_fetch.run(
        ctx,
        tick_data=tick_data,
        queries=["news lang:en"],
        authenticated_user_id="42",
    )

    assert result.ok
    assert ctx.get("search_references")["search_reference_tweets"][0]["id"] == "1"
    tick_data.compile_search_reference_tweets.assert_called_once_with(
        "acct1",
        queries=["news lang:en"],
        slot="2026-06-08-10",
        authenticated_user_id="42",
    )

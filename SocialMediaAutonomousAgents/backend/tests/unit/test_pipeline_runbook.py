"""Readable runbook and hidden service wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.pipeline import runbook, subagents
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.service import reset_pipeline


@pytest.fixture(autouse=True)
def _fresh() -> None:
    reset_pipeline()
    yield
    reset_pipeline()


def test_runbook_step_names_are_readable() -> None:
    names = [name for name, _ in POST_TICK_REFERENCE_STEPS]
    assert names == [
        "profile",
        "timeline_pool",
        "search_pool",
        "merge_reference_pools",
        "own_posts_pool",
        "timeline_analysis",
        "own_posts_analysis",
    ]


def test_runbook_reference_analysis_with_mocked_deps() -> None:
    tick_data = MagicMock()
    tick_data.compile_account_bundle.return_value = {"profile": {"id": "99"}}
    tick_data.compile_timeline_reference_tweets.return_value = {
        "timeline_reference_tweets": [
            {
                "id": "t1",
                "text": "story https://example.com/a",
                "like_count": 10,
                "reply_count": 2,
                "retweet_count": 1,
                "impression_count": 100,
            }
        ],
    }

    post_registry = MagicMock()
    post_registry.list_for_account.return_value = []
    post_registry.list_tweet_ids.return_value = []

    deps = PostRunDeps(
        tick_data=tick_data,
        repo=MagicMock(),
        post_registry=post_registry,
    )

    result = runbook.reference_analysis("acct1", niche="News", deps=deps)
    assert result.ok
    assert result.ctx.get("timeline_analysis") is not None
    assert result.reference_context()["own_posts"]["skipped"] is True


def test_subagents_exposed_on_package() -> None:
    assert callable(subagents.timeline.run)
    assert callable(subagents.own_posts.run)

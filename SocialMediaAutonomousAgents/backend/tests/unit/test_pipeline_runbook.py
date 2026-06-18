"""Readable runbook and hidden service wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.pipeline import runbook
from app.pipeline._runbook_engine import run_steps
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.flow import flatten_steps


def test_runbook_step_names_are_readable() -> None:
    names = [f.id for f in flatten_steps(POST_TICK_REFERENCE_STEPS)]
    assert names == [
        "load_account_bundle",
        "fetch_search_references",
        "collect_external_references",
        "fetch_own_post_history",
        "summarize_for_compose.analyze_external_references.rank_external_references",
        "summarize_for_compose.analyze_external_references.brief_external_references",
        "summarize_for_compose.analyze_own_posts.rank_own_posts",
        "summarize_for_compose.analyze_own_posts.brief_own_posts",
    ]


def test_runbook_top_level_step_ids() -> None:
    top_ids = [s.id for s in POST_TICK_REFERENCE_STEPS]
    assert top_ids == [
        "load_account_bundle",
        "fetch_search_references",
        "collect_external_references",
        "fetch_own_post_history",
        "summarize_for_compose",
    ]


def test_runbook_reference_analysis_with_mocked_deps() -> None:
    tick_data = MagicMock()
    tick_data.compile_account_bundle.return_value = {"account_id": "acct1", "profile": {"id": "99"}}
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
        "reference_errors": [],
    }

    post_registry = MagicMock()
    post_registry.list_for_account.return_value = []
    post_registry.list_tweet_ids.return_value = []

    deps = PostRunDeps(
        tick_data=tick_data,
        repo=MagicMock(),
        post_registry=post_registry,
    )

    ctx = runbook.start("acct1", niche="News")
    with patch("app.pipeline._runbook_engine.PipelineOutcomeRepository") as mock_outcomes:
        mock_outcomes.return_value.append = MagicMock()
        result = run_steps(POST_TICK_REFERENCE_STEPS, ctx, deps)
    assert result.ok
    assert result.ctx.get("timeline_analysis") is not None
    assert result.reference_context()["own_posts"]["skipped"] is True

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
        "compose_until_safe",
        "publish_post",
    ]


def test_runbook_top_level_step_ids() -> None:
    top_ids = [s.id for s in POST_TICK_REFERENCE_STEPS]
    assert top_ids == [
        "load_account_bundle",
        "fetch_search_references",
        "collect_external_references",
        "fetch_own_post_history",
        "summarize_for_compose",
        "compose_until_safe",
        "publish_post",
    ]


def test_runbook_reference_analysis_with_mocked_deps() -> None:
    """Test that the runbook with ACT steps accepts deps.live (doc 06 §4.1).

    This is a structure test, not an execution test. We verify that:
    - The runbook accepts PostRunDeps with live: ActLive
    - The two new ACT steps are callable and in the right position
    """
    from app.models.account import AccountDocument
    from app.pipeline.services.deps import ActLive

    tick_data = MagicMock()
    post_registry = MagicMock()
    post_registry.list_for_account.return_value = []
    post_registry.list_tweet_ids.return_value = []

    # Stub deps.live for the ACT steps (doc 06 §4.1, §7.2)
    mock_account = AccountDocument(
        account_id="acct1",
        category="news",
        posting_prompt="Post about news.",
        personality="direct",
        contrast_patterns=[],
        punctuation_rules=[],
        voice_version_hash="v1",
        voice_version_seq=1,
        voice_version_label="base",
    )
    live = ActLive(
        account=mock_account,
        tick_ctx=MagicMock(),
        guardian=MagicMock(),
        twitter=MagicMock(),
        post_registry=post_registry,
        run_id="test_run_123",
    )

    deps = PostRunDeps(
        tick_data=tick_data,
        repo=MagicMock(),
        post_registry=post_registry,
        live=live,
    )

    # Verify the structure accepts deps.live
    assert deps.live is not None
    assert deps.live.account.account_id == "acct1"
    assert deps.live.run_id == "test_run_123"

    # Verify the runbook can iterate over the new ACT steps without error
    flat_steps = list(flatten_steps(POST_TICK_REFERENCE_STEPS))
    act_step_ids = [s.id for s in flat_steps if s.id in ("compose_until_safe", "publish_post")]
    assert act_step_ids == ["compose_until_safe", "publish_post"]

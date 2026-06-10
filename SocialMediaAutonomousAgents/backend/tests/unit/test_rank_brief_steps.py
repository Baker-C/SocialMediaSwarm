"""Expanded rank and brief runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext


def test_rank_external_skips_when_no_urls() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    ctx.set_artifact(
        ArtifactKey.TIMELINE_REFERENCES,
        {
            "timeline_reference_tweets": [{"id": "1", "text": "no link here"}],
            "reference_errors": [],
        },
    )
    result = steps.rank_external_references(ctx, PostRunDeps(tick_data=MagicMock(), repo=MagicMock()))
    assert result.skipped
    assert result.skip_reason == "no_reference_with_urls"
    ranked = ctx.get("timeline_ranked")
    assert ranked["ranked"] == []


def test_brief_external_skips_when_ranked_empty() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1", niche="News")
    ctx.set_artifact(ArtifactKey.TIMELINE_RANKED, {"ranked": [], "winner": None})
    result = steps.brief_external_references(ctx, PostRunDeps(tick_data=MagicMock(), repo=MagicMock()))
    assert result.skipped
    analysis = ctx.get("timeline_analysis")
    assert analysis["skipped"] is True


def test_rank_own_posts_skips_insufficient_history() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    ctx.set_artifact(
        ArtifactKey.OWN_POSTS,
        {
            "account_id": "a1",
            "tweet_ids": ["p1"],
            "posts": [{"account_id": "a1", "tweet_id": "p1"}],
        },
    )
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock(), post_registry=MagicMock())
    result = steps.rank_own_posts(ctx, deps)
    assert result.skipped
    assert result.skip_reason == "insufficient_own_posts"


def test_brief_own_posts_skips_without_registry() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock(), post_registry=None)
    result = steps.brief_own_posts(ctx, deps)
    assert result.skipped
    assert ctx.get("own_posts_analysis")["skip_reason"] == "no_post_registry"

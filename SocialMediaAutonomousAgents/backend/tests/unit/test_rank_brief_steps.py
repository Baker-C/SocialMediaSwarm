"""Expanded rank and brief runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.tools.deterministic import reference_rank
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult


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


def _capture_top_n(monkeypatch) -> list[int]:
    """Monkeypatch reference_rank.run to record the top_n it receives."""
    captured: list[int] = []

    def fake_run(ctx, **kwargs):  # noqa: ANN001, ANN003
        captured.append(kwargs.get("top_n"))
        return StepResult(ok=True, payload={"ranked": [], "winner": None})

    monkeypatch.setattr(reference_rank, "run", fake_run)
    return captured


def test_rank_external_references_honors_top_n_config(monkeypatch) -> None:
    captured = _capture_top_n(monkeypatch)
    ctx = TickRunContext(account_id="a1", slot="s1")
    ctx.set_artifact(
        ArtifactKey.TIMELINE_REFERENCES,
        {"timeline_reference_tweets": [{"id": "1", "text": "ride this https://t.co/x"}]},
    )
    ctx.data["_step_config:deterministic.reference_rank"] = {"top_n": 15}
    steps.rank_external_references(ctx, PostRunDeps(tick_data=MagicMock(), repo=MagicMock()))
    assert captured == [15]


def test_rank_external_references_defaults_without_config(monkeypatch) -> None:
    captured = _capture_top_n(monkeypatch)
    ctx = TickRunContext(account_id="a1", slot="s1")
    ctx.set_artifact(
        ArtifactKey.TIMELINE_REFERENCES,
        {"timeline_reference_tweets": [{"id": "1", "text": "ride this https://t.co/x"}]},
    )
    steps.rank_external_references(ctx, PostRunDeps(tick_data=MagicMock(), repo=MagicMock()))
    assert captured == [steps.MIN_TOP_N]


def test_rank_own_posts_honors_top_n_config(monkeypatch) -> None:
    captured = _capture_top_n(monkeypatch)
    ctx = TickRunContext(account_id="a1", slot="s1")
    posts = [{"account_id": "a1", "tweet_id": f"p{i}"} for i in range(steps.MIN_OWN_POSTS + 1)]
    ctx.set_artifact(ArtifactKey.OWN_POSTS, {"account_id": "a1", "posts": posts})
    ctx.data["_step_config:deterministic.reference_rank"] = {"top_n": 15}
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock(), post_registry=MagicMock())
    steps.rank_own_posts(ctx, deps)
    assert captured == [15]

"""fetch_search_references runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.niche import Niche
from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.tools.data import search_fetch
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult


def test_fetch_search_references_skipped_when_no_search_topics() -> None:
    # Search topics come from niches → live trends → category, in that order. With no
    # niches, no twitter (so no trends), and no category, the step has nothing to query
    # and skips with "no_search_topics" (the niche→category refactor renamed this reason).
    ctx = TickRunContext(account_id="acct", slot="s1")
    repo = MagicMock()
    acc = MagicMock()
    acc.niches = []
    acc.category = ""  # no category fallback either → genuinely no search topics
    repo.load.return_value = acc
    deps = PostRunDeps(tick_data=MagicMock(), repo=repo, post_registry=MagicMock())
    result = steps.fetch_search_references(ctx, deps)
    assert result.skipped and result.skip_reason == "no_search_topics"


def test_fetch_search_references_one_call_per_niche_capped() -> None:
    ctx = TickRunContext(account_id="acct", slot="s1")
    repo = MagicMock()
    acc = MagicMock()
    acc.niches = [Niche(niche="protest drama"), Niche(niche="celeb feud")]
    repo.load.return_value = acc
    tick_data = MagicMock()
    tick_data.compile_search_reference_tweets.return_value = {"search_reference_tweets": []}
    deps = PostRunDeps(tick_data=tick_data, repo=repo, post_registry=MagicMock())
    steps.fetch_search_references(ctx, deps)
    kwargs = tick_data.compile_search_reference_tweets.call_args.kwargs
    assert kwargs["queries"] == ["protest drama", "celeb feud"]
    assert kwargs["max_results_per_query"] == steps.SEARCH_RESULTS_PER_NICHE == 50


def _capture_max_results(monkeypatch) -> list[int]:
    """Monkeypatch search_fetch.run to record the max_results_per_query it receives."""
    captured: list[int] = []

    def fake_run(ctx, **kwargs):  # noqa: ANN001, ANN003
        captured.append(kwargs.get("max_results_per_query"))
        return StepResult(ok=True, payload={})

    monkeypatch.setattr(search_fetch, "run", fake_run)
    return captured


def _niche_deps() -> PostRunDeps:
    repo = MagicMock()
    acc = MagicMock()
    acc.niches = [Niche(niche="protest drama")]
    repo.load.return_value = acc
    return PostRunDeps(tick_data=MagicMock(), repo=repo, post_registry=MagicMock())


def test_fetch_search_references_honors_max_results_config(monkeypatch) -> None:
    captured = _capture_max_results(monkeypatch)
    ctx = TickRunContext(account_id="acct", slot="s1")
    ctx.data["_step_config:data.search_fetch"] = {"max_results_per_query": 15}
    steps.fetch_search_references(ctx, _niche_deps())
    assert captured == [15]


def test_fetch_search_references_defaults_without_config(monkeypatch) -> None:
    captured = _capture_max_results(monkeypatch)
    ctx = TickRunContext(account_id="acct", slot="s1")
    steps.fetch_search_references(ctx, _niche_deps())
    assert captured == [steps.SEARCH_RESULTS_PER_NICHE]

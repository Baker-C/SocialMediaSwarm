"""fetch_search_references runbook step tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.niche import Niche
from app.pipeline.services import steps
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext


def test_fetch_search_references_skipped_when_no_search_topics() -> None:
    # Search topics come from niches → live trends → category, in that order. With no
    # niches, no twitter (so no trends), and no category, the step has nothing to query
    # and skips with "no_search_topics" (the niche→category refactor renamed this reason).
    ctx = TickRunContext(account_id="acct", slot="s1")
    repo = MagicMock()
    acc = MagicMock()
    acc.niches = []
    acc.category = ""
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

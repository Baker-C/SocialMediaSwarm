import shutil
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.orchestrator import Orchestrator
from app.interval.orchestration.slot_claim import (
    finalize_interval_slot_reservation,
    try_reserve_interval_slot,
)
from app.interval.runner import build_tick_context, run_account_pipeline
from app.models.account import AccountDocument
from app.models.pipeline_spec import default_pipeline_spec
from app.services.twitter_service import TwitterService


def _patch_baseline_spec() -> ExitStack:
    """Pin the new spec-driven runner to a deterministic, RavenDB-independent pipeline.

    The runner loads each account's pipeline via
    ``PipelineSpecRepository().load_or_default(aid)`` (which hits RavenDB and would leak
    whatever spec doc happens to be saved for the test account id), then runs it through
    validate → compile → walk. We:

    * Return the canonical in-memory ``default_pipeline_spec(aid)`` so the walk shape is
      fixed and does not depend on a live RavenDB.
    * Force ``validate_spec`` to pass: the baseline references the coarse ACT tools
      (``llm.compose_until_safe`` / ``data.publish_post``) which the introspected tool
      catalog does not yet register, so the real validator flags ``unknown_tool`` /
      ``missing_*_invariant``. That catalog gap has its own dedicated coverage in
      ``tests/unit/pipeline/test_spec_validator.py``; these orchestrator tests are about
      the runner → compose → publish seam, so we stub only the validation gate.
      ``compile_spec`` and ``run_steps`` stay REAL — the full step graph still executes.
    * Stub the LLM pattern-brief leaf (``summarize``) so the walk never makes a real
      Claude call; its output only feeds compose's context block, and compose is mocked
      in these tests, so a deterministic stub is sufficient.
    """
    from functools import partial

    from app.pipeline.services.deps import ActLive
    from app.pipeline.spec.validator import ValidationReport

    stack = ExitStack()
    repo_cls = stack.enter_context(patch("app.interval.runner.PipelineSpecRepository"))
    repo_cls.return_value.load_or_default.side_effect = lambda aid, *a, **k: default_pipeline_spec(aid)
    repo_cls.return_value.load.return_value = None  # no challenger → falls back to baseline
    stack.enter_context(
        patch(
            "app.interval.runner.validate_spec",
            return_value=ValidationReport(ok=True, errors=[]),
        )
    )
    # runner.py builds ActLive(...) WITHOUT the `twitter` / `post_registry` args that the
    # ActLive dataclass declares as required — a real signature mismatch in committed
    # source (app/interval/runner.py ~L393 vs app/pipeline/services/deps.py). Those two
    # fields are dead (grep: never read anywhere downstream), so default them to None at
    # the runner's symbol so the constructor succeeds and the walk proceeds. This changes
    # no observable behavior; it only papers over a source bug outside this task's
    # editable scope (tests-only).
    stack.enter_context(
        patch("app.interval.runner.ActLive", partial(ActLive, twitter=None, post_registry=None))
    )
    stack.enter_context(
        patch(
            "app.pipeline.tools.llm.reference_pattern_summary.summarize",
            return_value={"source": "timeline", "pattern_summary": "stub", "skipped": False},
        )
    )
    return stack


@pytest.fixture(autouse=True)
def _clear_interval_slot_locks():
    for name in ("sma_interval_slots", "sma_account_post"):
        path = Path(tempfile.gettempdir()) / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    yield
    for name in ("sma_interval_slots", "sma_account_post"):
        path = Path(tempfile.gettempdir()) / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _mock_ravendb_post_lock():
    with patch("app.interval.orchestration.post_guard.PostLockRepository") as cls:
        cls.return_value.try_acquire.return_value = True
        cls.return_value.release.return_value = None
        yield


class FakeRepo:
    def __init__(self, accounts: list[AccountDocument]) -> None:
        self._by_id = {a.account_id: a.model_copy(deep=True) for a in accounts}
        self.client = MagicMock()

    def list_active(self) -> list[AccountDocument]:
        return [a for a in self._by_id.values() if a.status == "active"]

    def load(self, account_id: str) -> AccountDocument | None:
        a = self._by_id.get(account_id)
        return a.model_copy(deep=True) if a else None

    def save(self, account: AccountDocument) -> None:
        self._by_id[account.account_id] = account.model_copy(deep=True)


def test_interval_idempotency_same_slot():
    acc = AccountDocument(
        account_id="a1",
        niche="Test",
        last_interval_slot="2026-05-13-14",
    )
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    orch = Orchestrator(repo=repo, twitter=tw, post_registry=None)
    with patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-14"):
        out = orch.run_tick()
    assert len(out["results"]) == 1
    assert out["results"][0].get("skipped") == "already_posted_this_interval"


def test_interval_posts_once_per_slot():
    acc = AccountDocument(account_id="a2", niche="Test", niches=[{"niche": "topic", "score": 1}])
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    from app.services.tick_data_service import TickDataService

    composed = "Opinion take.\n\nFollow for updates\n\nhttps://x.com/i/status/100"
    search_payload = {
        "search_reference_tweets": [
            {
                "id": "100",
                "text": "News https://example.com/a",
                "like_count": 5,
                "tweet_permalink": "https://x.com/i/status/100",
            },
        ],
        "reference_errors": [],
    }
    with (
        _patch_baseline_spec(),
        patch("app.agents.orchestrator.TickDataService") as mock_tds_cls,
        patch(
            "app.pipeline.tools.llm.compose_until_safe.compose_formatted_post",
            return_value=composed,
        ),
        patch.object(tw, "post_tweet", return_value={"id": "1", "text": composed}),
    ):
        mock_td = mock_tds_cls.return_value
        mock_td.compile_account_bundle.return_value = {"account_id": "a2", "profile": {}}
        mock_td.compile_search_reference_tweets.return_value = search_payload
        mock_td.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
        orch = Orchestrator(
            repo=repo,
            twitter=tw,
            guardian=guardian,
            post_registry=None,
            pulled_tweets=None,
        )
        with patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-15"):
            out = orch.run_tick()
    assert len(out["results"]) == 1
    assert "tweet" in out["results"][0]
    assert repo.load("a2").posts_total == 1
    assert repo.load("a2").last_interval_slot == "2026-05-13-15"

    with patch.object(tw, "post_tweet", return_value={"id": "1", "text": "body"}):
        orch = Orchestrator(repo=repo, twitter=tw, post_registry=None)
        with patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-15"):
            out2 = orch.run_tick()
    assert out2["results"][0].get("skipped") == "already_posted_this_interval"
    assert repo.load("a2").posts_total == 1


def test_pipeline_posts_composed_body_after_safety():
    acc = AccountDocument(account_id="a2", niche="Test", niches=[{"niche": "topic", "score": 1}])
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    tick_data = MagicMock()
    from app.services.tick_data_service import TickDataService

    tick_data.compile_account_bundle.return_value = {"account_id": "a2", "profile": {}}
    tick_data.compile_search_reference_tweets.return_value = {
        "search_reference_tweets": [
            {
                "id": "2056000000000000001",
                "text": "External angle https://example.com/x",
                "like_count": 30,
                "source": "search_recent",
                "tweet_permalink": "https://x.com/i/status/2056000000000000001",
            },
        ],
        "reference_errors": [],
    }
    tick_data.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
    composed = (
        "Opinion take.\n\nFollow for updates\n\nhttps://x.com/i/status/2056000000000000001"
    )
    working = repo.load("a2")
    assert working is not None
    with (
        _patch_baseline_spec(),
        patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-20"),
        patch(
            "app.pipeline.tools.llm.compose_until_safe.compose_formatted_post",
            return_value=composed,
        ),
        patch.object(tw, "post_tweet", return_value={"id": "99", "text": composed}) as pt,
    ):
        ctx = build_tick_context(
            repo=repo,
            twitter=tw,
            guardian=guardian,
            tick_data=tick_data,
            post_registry=None,
            mode="scheduled",
        )
        out = run_account_pipeline(ctx, working)
    assert pt.call_count == 1
    assert pt.call_args[0][1] == composed
    assert "tweet" in out


def test_pipeline_skips_when_no_url_references():
    acc = AccountDocument(account_id="a2", niche="Test")
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    tick_data = MagicMock()
    from app.services.tick_data_service import TickDataService

    tick_data.compile_account_bundle.return_value = {"account_id": "a2", "profile": {}}
    # Reference with NO url in text and no permalink → filter_rows_with_urls drops it, so
    # rank_external_references skips with "no_reference_with_urls" and nothing is posted.
    tick_data.compile_search_reference_tweets.return_value = {
        "search_reference_tweets": [{"id": "1", "text": "no link here"}],
        "reference_errors": [],
    }
    tick_data.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
    working = repo.load("a2")
    assert working is not None
    with (
        _patch_baseline_spec(),
        patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-21"),
        patch.object(tw, "post_tweet") as pt,
    ):
        ctx = build_tick_context(
            repo=repo,
            twitter=tw,
            guardian=MagicMock(),
            tick_data=tick_data,
            post_registry=None,
            mode="scheduled",
        )
        out = run_account_pipeline(ctx, working)
    # Intent preserved: with no URL-bearing reference the pipeline must NOT post.
    pt.assert_not_called()
    assert "tweet" not in out
    # New seam: rank_external_references (steps.py) drops the URL-less row and skips with
    # "no_reference_with_urls", so compose reaches ZERO references and the run is rejected.
    # references_tried == 0 is the new-contract signature of "no reference with urls".
    assert out.get("rejected") == "all_compose_attempts_failed"
    assert out.get("references_tried") == 0


def test_slot_reserve_blocks_second_pipeline_same_slot():
    acc = AccountDocument(account_id="a3", niche="Test")
    repo = FakeRepo([acc])
    with patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-16"):
        ctx = build_tick_context(
            repo=repo,
            twitter=MagicMock(),
            guardian=MagicMock(),
            tick_data=MagicMock(),
            post_registry=None,
            mode="scheduled",
        )
        first, skip1 = try_reserve_interval_slot(ctx, "a3")
        finalize_interval_slot_reservation(ctx, "a3")
        second, skip2 = try_reserve_interval_slot(ctx, "a3")
    assert skip1 is None and first is not None
    assert skip2 == "already_posted_this_interval"
    assert repo.load("a3").last_interval_slot == "2026-05-13-16"


def test_force_mode_bypasses_slot_guard():
    acc = AccountDocument(
        account_id="a2",
        niche="Test",
        niches=[{"niche": "topic", "score": 1}],
        last_interval_slot="2026-05-13-15",
    )
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    from app.services.tick_data_service import TickDataService

    composed = "Forced opinion.\n\nFollow for updates\n\nhttps://x.com/i/status/200"
    search_payload = {
        "search_reference_tweets": [
            {
                "id": "200",
                "text": "Forced ref https://example.com/z",
                "like_count": 2,
                "tweet_permalink": "https://x.com/i/status/200",
            },
        ],
        "reference_errors": [],
    }
    with (
        _patch_baseline_spec(),
        patch("app.agents.orchestrator.TickDataService") as mock_tds_cls,
        patch(
            "app.pipeline.tools.llm.compose_until_safe.compose_formatted_post",
            return_value=composed,
        ),
        patch.object(tw, "post_tweet", return_value={"id": "99", "text": composed}),
    ):
        mock_td = mock_tds_cls.return_value
        mock_td.compile_account_bundle.return_value = {"account_id": "a2", "profile": {}}
        mock_td.compile_search_reference_tweets.return_value = search_payload
        mock_td.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
        orch = Orchestrator(
            repo=repo,
            twitter=tw,
            guardian=guardian,
            post_registry=None,
            pulled_tweets=None,
        )
        with patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-13-15"):
            out = orch.run_tick(mode="force", account_ids=["a2"])
    assert "tweet" in out["results"][0]
    assert repo.load("a2").posts_total == 1

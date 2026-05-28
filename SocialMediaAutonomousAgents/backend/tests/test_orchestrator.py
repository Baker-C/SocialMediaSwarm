import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.orchestrator import Orchestrator
from app.hourly.orchestration.slot_claim import (
    finalize_hourly_slot_reservation,
    try_reserve_hourly_slot,
)
from app.hourly.runner import build_tick_context, run_account_pipeline
from app.models.account import AccountDocument
from app.services.twitter_service import TwitterService


@pytest.fixture(autouse=True)
def _clear_hourly_slot_locks():
    for name in ("sma_hourly_slots", "sma_account_post"):
        path = Path(tempfile.gettempdir()) / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    yield
    for name in ("sma_hourly_slots", "sma_account_post"):
        path = Path(tempfile.gettempdir()) / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _mock_ravendb_post_lock():
    with patch("app.hourly.orchestration.post_guard.PostLockRepository") as cls:
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


def test_hourly_idempotency_same_slot():
    acc = AccountDocument(
        account_id="a1",
        niche="Test",
        last_post_slot="2026-05-13-14",
    )
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    orch = Orchestrator(repo=repo, twitter=tw, post_registry=None)
    with patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-14"):
        out = orch.run_tick()
    assert len(out["results"]) == 1
    assert out["results"][0].get("skipped") == "already_posted_this_hour"


def test_hourly_posts_once_per_slot():
    acc = AccountDocument(account_id="a2", niche="Test")
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    from app.services.tick_data_service import TickDataService

    composed = "Opinion take.\n\nFollow for updates\n\nhttps://x.com/i/status/100"
    timeline_payload = {
        "timeline_reference_tweets": [
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
        patch("app.agents.orchestrator.TickDataService") as mock_tds_cls,
        patch("app.hourly.runner.compose_formatted_post", return_value=composed),
        patch.object(tw, "post_tweet", return_value={"id": "1", "text": composed}),
    ):
        mock_td = mock_tds_cls.return_value
        mock_td.compile_account_bundle.return_value = {"profile": {}}
        mock_td.compile_timeline_reference_tweets.return_value = timeline_payload
        mock_td.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
        orch = Orchestrator(
            repo=repo,
            twitter=tw,
            guardian=guardian,
            creator=MagicMock(),
            post_registry=None,
            pulled_tweets=None,
        )
        with patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-15"):
            out = orch.run_tick()
    assert len(out["results"]) == 1
    assert "tweet" in out["results"][0]
    assert repo.load("a2").posts_total == 1
    assert repo.load("a2").last_post_slot == "2026-05-13-15"

    with patch.object(tw, "post_tweet", return_value={"id": "1", "text": "body"}):
        orch = Orchestrator(repo=repo, twitter=tw, post_registry=None)
        with patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-15"):
            out2 = orch.run_tick()
    assert out2["results"][0].get("skipped") == "already_posted_this_hour"
    assert repo.load("a2").posts_total == 1


def test_pipeline_posts_composed_body_after_safety():
    acc = AccountDocument(account_id="a2", niche="Test")
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    tick_data = MagicMock()
    from app.services.tick_data_service import TickDataService

    tick_data.compile_account_bundle.return_value = {"profile": {}}
    tick_data.compile_timeline_reference_tweets.return_value = {
        "timeline_reference_tweets": [
            {
                "id": "2056000000000000001",
                "text": "External angle https://example.com/x",
                "like_count": 30,
                "source": "following_timeline",
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
        patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-20"),
        patch("app.hourly.runner.compose_formatted_post", return_value=composed),
        patch.object(tw, "post_tweet", return_value={"id": "99", "text": composed}) as pt,
    ):
        ctx = build_tick_context(
            repo=repo,
            twitter=tw,
            creator=MagicMock(),
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

    tick_data.compile_account_bundle.return_value = {"profile": {}}
    tick_data.compile_timeline_reference_tweets.return_value = {
        "timeline_reference_tweets": [{"id": "1", "text": "no link here"}],
        "reference_errors": [],
    }
    tick_data.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
    working = repo.load("a2")
    assert working is not None
    with (
        patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-21"),
        patch.object(tw, "post_tweet") as pt,
    ):
        ctx = build_tick_context(
            repo=repo,
            twitter=tw,
            creator=MagicMock(),
            guardian=MagicMock(),
            tick_data=tick_data,
            post_registry=None,
            mode="scheduled",
        )
        out = run_account_pipeline(ctx, working)
    pt.assert_not_called()
    assert out.get("skipped") == "no_reference_with_urls"


def test_slot_reserve_blocks_second_pipeline_same_slot():
    acc = AccountDocument(account_id="a3", niche="Test")
    repo = FakeRepo([acc])
    with patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-16"):
        ctx = build_tick_context(
            repo=repo,
            twitter=MagicMock(),
            creator=MagicMock(),
            guardian=MagicMock(),
            tick_data=MagicMock(),
            post_registry=None,
            mode="scheduled",
        )
        first, skip1 = try_reserve_hourly_slot(ctx, "a3")
        finalize_hourly_slot_reservation(ctx, "a3")
        second, skip2 = try_reserve_hourly_slot(ctx, "a3")
    assert skip1 is None and first is not None
    assert skip2 == "already_posted_this_hour"
    assert repo.load("a3").last_post_slot == "2026-05-13-16"


def test_force_mode_bypasses_slot_guard():
    acc = AccountDocument(
        account_id="a2",
        niche="Test",
        last_post_slot="2026-05-13-15",
    )
    repo = FakeRepo([acc])
    tw = TwitterService(repo)
    guardian = MagicMock()
    guardian.evaluate.return_value = (True, "")
    from app.services.tick_data_service import TickDataService

    composed = "Forced opinion.\n\nFollow for updates\n\nhttps://x.com/i/status/200"
    timeline_payload = {
        "timeline_reference_tweets": [
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
        patch("app.agents.orchestrator.TickDataService") as mock_tds_cls,
        patch("app.hourly.runner.compose_formatted_post", return_value=composed),
        patch.object(tw, "post_tweet", return_value={"id": "99", "text": composed}),
    ):
        mock_td = mock_tds_cls.return_value
        mock_td.compile_account_bundle.return_value = {"profile": {}}
        mock_td.compile_timeline_reference_tweets.return_value = timeline_payload
        mock_td.merge_reference_pool.side_effect = TickDataService.merge_reference_pool
        orch = Orchestrator(
            repo=repo,
            twitter=tw,
            guardian=guardian,
            creator=MagicMock(),
            post_registry=None,
            pulled_tweets=None,
        )
        with patch("app.hourly.runner.current_post_slot_key", return_value="2026-05-13-15"):
            out = orch.run_tick(mode="force", account_ids=["a2"])
    assert "tweet" in out["results"][0]
    assert repo.load("a2").posts_total == 1

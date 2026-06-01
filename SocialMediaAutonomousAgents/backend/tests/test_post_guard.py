from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.interval.context import TickContext
from app.interval.orchestration.post_guard import check_post_cooldown, try_begin_post
from app.models.account import AccountDocument


def _ctx(*, bypass: bool = False) -> TickContext:
    return TickContext(
        repo=MagicMock(),
        twitter=MagicMock(),
        creator=MagicMock(),
        guardian=MagicMock(),
        tick_data=MagicMock(),
        post_registry=None,
        slot="2026-05-17-03",
        now_iso=datetime.now(timezone.utc).isoformat(),
        mode="force",
        force_account_ids=frozenset({"a1"}),
        bypass_post_cooldown=bypass,
    )


def test_cooldown_blocks_recent_post():
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    acc = AccountDocument(account_id="a1", niche="T", last_post_at=recent)
    with patch("app.interval.orchestration.post_guard.settings") as s:
        s.post_cooldown_minutes = 55
        assert check_post_cooldown(acc, bypass=False) is not None


def test_cooldown_bypass_flag():
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    acc = AccountDocument(account_id="a1", niche="T", last_post_at=recent)
    with patch("app.interval.orchestration.post_guard.settings") as s:
        s.post_cooldown_minutes = 55
        assert check_post_cooldown(acc, bypass=True) is None


def test_try_begin_post_acquires_locks():
    import shutil
    import tempfile
    from pathlib import Path

    acc = AccountDocument(account_id="guard_test_a1", niche="T")
    ctx = _ctx()
    lock_repo = MagicMock()
    lock_repo.try_acquire.return_value = True
    path = Path(tempfile.gettempdir()) / "sma_account_post"
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    with (
        patch("app.interval.orchestration.post_guard.PostLockRepository", return_value=lock_repo),
        patch("app.interval.orchestration.post_guard.settings") as s,
    ):
        s.post_cooldown_minutes = 0
        s.post_lock_ttl_seconds = 600
        out_acc, skip = try_begin_post(ctx, "guard_test_a1", acc)
    assert skip is None
    assert out_acc is acc
    assert ctx.active_post_locks["guard_test_a1"]

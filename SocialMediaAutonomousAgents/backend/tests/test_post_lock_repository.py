"""Post lock repository behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services.post_lock_repository import PostLockRepository


def test_try_acquire_replaces_expired_lock() -> None:
    client = MagicMock()
    now = datetime.now(timezone.utc)
    expired_until = (now - timedelta(minutes=1)).isoformat()
    client.get_document.side_effect = [
        {"holder": "9999@slot", "until": expired_until},
        {"holder": "1234@slot", "until": (now + timedelta(minutes=10)).isoformat()},
    ]
    repo = PostLockRepository(client)
    assert repo.try_acquire("acct1", holder="1234@slot", ttl_seconds=600) is True
    client.put_document.assert_called_once()


def test_try_acquire_blocks_active_other_holder() -> None:
    client = MagicMock()
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=5)).isoformat()
    client.get_document.return_value = {"holder": "9999@slot", "until": future}
    repo = PostLockRepository(client)
    assert repo.try_acquire("acct1", holder="1234@slot", ttl_seconds=600) is False
    client.put_document.assert_not_called()


def test_is_expired() -> None:
    repo = PostLockRepository(MagicMock())
    now = datetime.now(timezone.utc)
    assert repo.is_expired({"until": (now - timedelta(seconds=1)).isoformat()}, now=now)
    assert not repo.is_expired({"until": (now + timedelta(seconds=30)).isoformat()}, now=now)

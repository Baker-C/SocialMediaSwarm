"""Cross-mode posting guards: cooldown, per-account lock, RavenDB claim."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.interval.context import TickContext
from app.interval.orchestration.slot_claim import release_interval_slot_reservation
from app.models.account import AccountDocument
from app.services.post_lock_repository import PostLockRepository

logger = logging.getLogger(__name__)

_POST_LOCKS: dict[str, threading.Lock] = {}
_POST_LOCKS_GUARD = threading.Lock()


def _account_thread_lock(account_id: str) -> threading.Lock:
    with _POST_LOCKS_GUARD:
        lock = _POST_LOCKS.get(account_id)
        if lock is None:
            lock = threading.Lock()
            _POST_LOCKS[account_id] = lock
        return lock


def _account_lock_path(account_id: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_id)
    return Path(tempfile.gettempdir()) / "sma_account_post" / f"{safe_id}.lock"


def _stale_file_lock_seconds() -> int:
    return max(30, int(settings.post_lock_ttl_seconds))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_post_cooldown(account: AccountDocument, *, bypass: bool) -> str | None:
    """Return skip reason if ``last_post_at`` is inside the configured cooldown window."""
    if bypass or settings.post_cooldown_minutes <= 0:
        return None
    last_at = _parse_iso(account.last_post_at)
    if last_at is None:
        return None
    elapsed = datetime.now(timezone.utc) - last_at
    if elapsed < timedelta(minutes=settings.post_cooldown_minutes):
        remaining = timedelta(minutes=settings.post_cooldown_minutes) - elapsed
        mins = max(1, int(remaining.total_seconds() // 60) + 1)
        return f"posted_within_cooldown_{mins}m"
    return None


def _is_stale_file_lock(lock_path: Path) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age > _stale_file_lock_seconds()


def _acquire_file_lock(lock_path: Path) -> bool:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        if _is_stale_file_lock(lock_path):
            logger.warning("removing stale account post file lock %s", lock_path)
            _release_file_lock(lock_path)
            return _acquire_file_lock(lock_path)
        return False


def _release_file_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def try_begin_post(
    ctx: TickContext,
    account_id: str,
    account: AccountDocument,
) -> tuple[AccountDocument | None, str | None]:
    """
    Cooldown + file lock + RavenDB claim before any pipeline work.

    Applies to scheduled and force modes (force can bypass cooldown via context flag).
    """
    cooldown_skip = check_post_cooldown(account, bypass=ctx.bypass_post_cooldown)
    if cooldown_skip:
        return None, cooldown_skip

    lock_path = _account_lock_path(account_id)
    holder = f"{os.getpid()}@{ctx.slot}"

    with _account_thread_lock(account_id):
        if not _acquire_file_lock(lock_path):
            return None, "account_post_lock_held"

        lock_repo = PostLockRepository(ctx.repo.client)
        if not lock_repo.try_acquire(
            account_id,
            holder=holder,
            ttl_seconds=settings.post_lock_ttl_seconds,
        ):
            _release_file_lock(lock_path)
            return None, "ravendb_post_lock_held"

        ctx.active_post_locks[account_id] = holder
        ctx.active_post_file_locks[account_id] = lock_path
        return account, None


def release_post_guard(ctx: TickContext, account_id: str) -> None:
    holder = ctx.active_post_locks.pop(account_id, None)
    lock_path = ctx.active_post_file_locks.pop(account_id, None)
    if holder:
        try:
            PostLockRepository(ctx.repo.client).release(account_id, holder=holder)
        except Exception as exc:
            logger.warning("release RavenDB post lock %s: %s", account_id, exc)
    if lock_path:
        _release_file_lock(lock_path)


def release_post_pipeline_guards(ctx: TickContext, account_id: str) -> None:
    """Revert slot reservation (if any) and release post locks for ``account_id``."""
    if account_id in ctx.slot_reservations:
        release_interval_slot_reservation(ctx, account_id)
    if account_id in ctx.active_post_locks:
        release_post_guard(ctx, account_id)

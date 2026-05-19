"""Hourly slot idempotency: reserve before LLM work, release on failure."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.hourly.context import TickContext
from app.models.account import AccountDocument

logger = logging.getLogger(__name__)

# Pipeline should finish well under this; stale locks are removed after crashes.
_STALE_LOCK_SECONDS = 30 * 60

_ACCOUNT_LOCKS: dict[str, threading.Lock] = {}
_ACCOUNT_LOCKS_GUARD = threading.Lock()


def _account_lock(account_id: str) -> threading.Lock:
    with _ACCOUNT_LOCKS_GUARD:
        lock = _ACCOUNT_LOCKS.get(account_id)
        if lock is None:
            lock = threading.Lock()
            _ACCOUNT_LOCKS[account_id] = lock
        return lock


def _slot_lock_path(account_id: str, slot: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_id)
    safe_slot = "".join(c if c.isalnum() or c in "-_" else "_" for c in slot)
    base = Path(tempfile.gettempdir()) / "sma_hourly_slots"
    return base / f"{safe_id}__{safe_slot}.lock"


@dataclass(frozen=True)
class SlotReservation:
    account: AccountDocument
    previous_slot: str | None
    lock_path: Path


def reload_account(ctx: TickContext, account_id: str) -> AccountDocument | None:
    return ctx.repo.load(account_id)


def try_reserve_hourly_slot(ctx: TickContext, account_id: str) -> tuple[SlotReservation | None, str | None]:
    """
    Reserve the current hourly slot for ``account_id`` (scheduled mode only).

    Returns ``(reservation, skip_reason)``. On success, ``last_post_slot`` is persisted
    before any expensive pipeline work so concurrent ticks/processes skip this hour.
    """
    if ctx.mode != "scheduled":
        fresh = reload_account(ctx, account_id)
        if fresh is None:
            return None, "account_not_found"
        return SlotReservation(account=fresh, previous_slot=fresh.last_post_slot, lock_path=Path()), None

    fresh = reload_account(ctx, account_id)
    if fresh is None:
        return None, "account_not_found"
    if fresh.last_post_slot == ctx.slot:
        return None, "already_posted_this_hour"

    lock_path = _slot_lock_path(account_id, ctx.slot)
    with _account_lock(account_id):
        if not _acquire_lock_file(lock_path):
            again = reload_account(ctx, account_id)
            if again is not None and again.last_post_slot == ctx.slot:
                return None, "already_posted_this_hour"
            logger.info(
                "hourly slot lock held elsewhere account_id=%s slot=%s",
                account_id,
                ctx.slot,
            )
            return None, "slot_lock_held"

        fresh = reload_account(ctx, account_id)
        if fresh is None:
            _release_lock_file(lock_path)
            return None, "account_not_found"
        if fresh.last_post_slot == ctx.slot:
            _release_lock_file(lock_path)
            return None, "already_posted_this_hour"

        previous_slot = fresh.last_post_slot
        fresh.last_post_slot = ctx.slot
        ctx.repo.save(fresh)

        verify = reload_account(ctx, account_id)
        if verify is None or verify.last_post_slot != ctx.slot:
            _release_lock_file(lock_path)
            return None, "slot_claim_lost"

        ctx.slot_reservations[account_id] = previous_slot
        return SlotReservation(account=verify, previous_slot=previous_slot, lock_path=lock_path), None


def finalize_hourly_slot_reservation(ctx: TickContext, account_id: str) -> None:
    """Drop the cross-process lock after a successful post; keep DB slot reserved."""
    if ctx.mode != "scheduled":
        return
    ctx.slot_reservations.pop(account_id, None)
    _release_lock_file(_slot_lock_path(account_id, ctx.slot))


def release_hourly_slot_reservation(ctx: TickContext, account_id: str) -> None:
    """Revert a failed tick so the same hour can be retried (scheduled mode only)."""
    if ctx.mode != "scheduled":
        return

    previous_slot = ctx.slot_reservations.pop(account_id, None)
    lock_path = _slot_lock_path(account_id, ctx.slot)

    with _account_lock(account_id):
        fresh = reload_account(ctx, account_id)
        if fresh is not None and fresh.last_post_slot == ctx.slot:
            fresh.last_post_slot = previous_slot
            ctx.repo.save(fresh)
        _release_lock_file(lock_path)


def _release_lock_file(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("could not remove slot lock %s: %s", lock_path, exc)


def _is_stale_lock(lock_path: Path) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age > _STALE_LOCK_SECONDS


def _acquire_lock_file(lock_path: Path) -> bool:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        if _is_stale_lock(lock_path):
            logger.warning("removing stale hourly slot lock %s", lock_path)
            _release_lock_file(lock_path)
            return _acquire_lock_file(lock_path)
        return False

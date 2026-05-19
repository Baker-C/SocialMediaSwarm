"""Ensure only one process runs APScheduler (avoids duplicate :00 jobs)."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK_PATH = Path(tempfile.gettempdir()) / "sma_apscheduler.lock"
_lock_fd: int | None = None


def try_acquire_scheduler_lock() -> bool:
    """Return True if this process should start APScheduler."""
    global _lock_fd
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        _lock_fd = fd
        return True
    except FileExistsError:
        logger.warning(
            "APScheduler not started: another process holds %s "
            "(set RUN_SCHEDULER=false on secondary workers)",
            _LOCK_PATH,
        )
        return False


def release_scheduler_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        try:
            os.close(_lock_fd)
        except OSError:
            pass
        _lock_fd = None
    try:
        _LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass

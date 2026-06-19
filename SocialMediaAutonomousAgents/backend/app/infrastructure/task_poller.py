"""Blocking poll helper for async provider jobs (submit → poll → result).

Tools stay synchronous: a step calls ``poll_until`` and blocks until the remote
job completes. The timeout is a safety backstop only — it converts a wedged or
dropped job into a clean error instead of an unbounded hang.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TaskPollError(RuntimeError):
    """The remote job reported a failure status."""


class TaskPollTimeout(TimeoutError):
    """The backstop timeout elapsed before the job completed."""


def poll_until(
    fetch: Callable[[], T],
    is_done: Callable[[T], bool],
    *,
    timeout_s: float,
    interval_s: float = 3.0,
    is_failed: Callable[[T], str | None] | None = None,
) -> T:
    """Poll ``fetch`` every ``interval_s`` until ``is_done`` is true.

    Raises ``TaskPollError`` if ``is_failed`` returns a message, or
    ``TaskPollTimeout`` once ``timeout_s`` elapses.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        result = fetch()
        if is_failed is not None:
            reason = is_failed(result)
            if reason:
                raise TaskPollError(reason)
        if is_done(result):
            return result
        if time.monotonic() >= deadline:
            raise TaskPollTimeout(f"Job did not complete within {timeout_s:.0f}s")
        time.sleep(interval_s)

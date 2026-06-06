"""Real-time progress callbacks for manual force-post runs."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable

ProgressCallback = Callable[[str, str, str], None]

_progress_cb: ContextVar[ProgressCallback | None] = ContextVar("force_post_progress", default=None)

FORCE_POST_STEP_ORDER: list[tuple[str, str]] = [
    ("start", "Starting pipeline"),
    ("load_account", "Loading account"),
    ("post_lock", "Acquiring post lock"),
    ("fetch_profile", "Fetching profile"),
    ("fetch_timeline", "Fetching timeline references"),
    ("rank_references", "Ranking references"),
    ("compose", "Composing post"),
    ("safety", "Safety review"),
    ("publish", "Publishing to X"),
    ("complete", "Done"),
]


def set_progress_callback(cb: ProgressCallback | None) -> None:
    _progress_cb.set(cb)


def reset_progress_callback(token: object) -> None:
    _progress_cb.reset(token)  # type: ignore[arg-type]


def progress_step(step_id: str, label: str | None = None, *, status: str = "active") -> None:
    cb = _progress_cb.get()
    if cb is None:
        return
    display = label or dict(FORCE_POST_STEP_ORDER).get(step_id, step_id)
    cb(step_id, display, status)


def progress_active(step_id: str, label: str | None = None) -> None:
    progress_step(step_id, label, status="active")


def progress_done(step_id: str, label: str | None = None) -> None:
    progress_step(step_id, label, status="done")


def progress_error(step_id: str, message: str) -> None:
    cb = _progress_cb.get()
    if cb is None:
        return
    display = dict(FORCE_POST_STEP_ORDER).get(step_id, step_id)
    cb(step_id, f"{display}: {message}", "error")


def run_with_progress(cb: ProgressCallback, fn: Callable[[], Any]) -> Any:
    token = _progress_cb.set(cb)
    try:
        progress_active("start")
        progress_done("start")
        return fn()
    finally:
        _progress_cb.reset(token)

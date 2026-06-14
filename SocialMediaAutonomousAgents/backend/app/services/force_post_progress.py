"""Backward-compatible re-exports for pipeline progress."""

from __future__ import annotations

from app.services.pipeline_progress import (
    ProgressCallback,
    progress_active,
    progress_done,
    progress_error,
    progress_step,
    reset_progress_callback,
    run_with_progress,
    set_progress_callback,
)

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

__all__ = [
    "FORCE_POST_STEP_ORDER",
    "ProgressCallback",
    "progress_active",
    "progress_done",
    "progress_error",
    "progress_step",
    "reset_progress_callback",
    "run_with_progress",
    "set_progress_callback",
]

"""Backward-compatible re-exports; implementation lives in app.interval."""

from __future__ import annotations

from app.interval.context import TickContext
from app.interval.orchestration.post_tick import phase3_global_persist, phase4_backup_noop
from app.interval.orchestration.pre_tick import phase1_global_setup
from app.interval.runner import (
    build_tick_context,
    current_interval_slot_key,
    run_account_pipeline,
    run_interval_tick,
)
from app.interval.schemas import TickMode

__all__ = [
    "TickContext",
    "TickMode",
    "build_tick_context",
    "current_interval_slot_key",
    "phase1_global_setup",
    "phase3_global_persist",
    "phase4_backup_noop",
    "run_account_pipeline",
    "run_interval_tick",
]

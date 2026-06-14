"""In-process event dispatcher: a ContextVar bus mirroring ``pipeline_progress``.

Emit sites call the transport-agnostic ``emit_*`` helpers; the dispatcher stamps
a monotonic ``seq`` and ``occurred_at`` and fans each event to its sinks. When no
dispatcher is set on the context (e.g. unit tests, NATS disabled), every emit is a
no-op — exactly like ``pipeline_progress.emit``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Protocol, Sequence

from app.pipeline.events.types import EventKind, PipelineEvent, StepScope

logger = logging.getLogger(__name__)


class EventSink(Protocol):
    def on_event(self, event: PipelineEvent) -> None: ...


class EventDispatcher:
    def __init__(
        self,
        *,
        run_id: str,
        account_id: str,
        slot: str,
        mode: str,
        sinks: Sequence[EventSink],
    ) -> None:
        self.run_id = run_id
        self.account_id = account_id
        self.slot = slot
        self.mode = mode
        self._sinks = list(sinks)
        self._seq = 0

    def emit(self, kind: EventKind, data: dict[str, Any] | None = None) -> PipelineEvent:
        self._seq += 1
        event = PipelineEvent(
            run_id=self.run_id,
            account_id=self.account_id,
            slot=self.slot,
            mode=self.mode,
            seq=self._seq,
            kind=kind,
            data=data or {},
        )
        for sink in self._sinks:
            try:
                sink.on_event(event)
            except Exception:
                logger.exception("event sink %s failed for %s", type(sink).__name__, kind)
        return event


_dispatcher: ContextVar[EventDispatcher | None] = ContextVar(
    "pipeline_event_dispatcher", default=None
)


@contextmanager
def run_events(
    *,
    run_id: str,
    account_id: str,
    slot: str,
    mode: str,
    sinks: Sequence[EventSink],
) -> Iterator[EventDispatcher]:
    """Bind a dispatcher for the duration of one pipeline run."""
    disp = EventDispatcher(run_id=run_id, account_id=account_id, slot=slot, mode=mode, sinks=sinks)
    token = _dispatcher.set(disp)
    try:
        yield disp
    finally:
        _dispatcher.reset(token)


def emit_event(kind: EventKind, data: dict[str, Any] | None = None) -> None:
    disp = _dispatcher.get()
    if disp is not None:
        disp.emit(kind, data)


def current_run_id() -> str | None:
    disp = _dispatcher.get()
    return disp.run_id if disp is not None else None


# --- convenience emitters -------------------------------------------------

def emit_run_started(*, niche: str = "") -> None:
    emit_event("run_started", {"niche": niche})


def emit_run_completed(
    *, status: str, duration_ms: int | None = None, summary: dict[str, Any] | None = None
) -> None:
    emit_event(
        "run_completed",
        {"status": status, "duration_ms": duration_ms, "summary": summary or {}},
    )


def emit_step_started(
    step_id: str,
    *,
    scope: StepScope,
    parent_id: str | None = None,
    purpose: str | None = None,
    inputs: list[dict[str, Any]] | None = None,
) -> None:
    emit_event(
        "step_started",
        {
            "step_id": step_id,
            "scope": scope,
            "parent_id": parent_id,
            "purpose": purpose,
            "inputs": inputs or [],
        },
    )


def emit_step_completed(
    step_id: str,
    *,
    scope: StepScope,
    parent_id: str | None = None,
    purpose: str | None = None,
    outputs: list[dict[str, Any]] | None = None,
    duration_ms: int | None = None,
) -> None:
    emit_event(
        "step_completed",
        {
            "step_id": step_id,
            "scope": scope,
            "parent_id": parent_id,
            "purpose": purpose,
            "outputs": outputs or [],
            "duration_ms": duration_ms,
        },
    )


def emit_step_skipped(
    step_id: str,
    *,
    scope: StepScope,
    parent_id: str | None = None,
    skip_reason: str | None = None,
    duration_ms: int | None = None,
) -> None:
    emit_event(
        "step_skipped",
        {
            "step_id": step_id,
            "scope": scope,
            "parent_id": parent_id,
            "skip_reason": skip_reason,
            "duration_ms": duration_ms,
        },
    )


def emit_step_failed(
    step_id: str,
    *,
    scope: StepScope,
    parent_id: str | None = None,
    error: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    emit_event(
        "step_failed",
        {
            "step_id": step_id,
            "scope": scope,
            "parent_id": parent_id,
            "error": error or {},
            "duration_ms": duration_ms,
        },
    )

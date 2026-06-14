"""Real-time progress callbacks for pipeline runs (force post and future live views)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal

ProgressScope = Literal["orchestrator", "runbook"]
ProgressStatus = Literal["active", "done", "error"]

ORCHESTRATOR_STEP_LABELS: dict[str, str] = {
    "start": "Starting pipeline",
    "load_account": "Loading account",
    "post_lock": "Acquiring post lock",
    "compose": "Composing post",
    "safety": "Safety review",
    "publish": "Publishing to X",
    "complete": "Done",
}

# Legacy coarse labels kept for linear force-post tracker projection.
LEGACY_STEP_LABELS: dict[str, str] = {
    **ORCHESTRATOR_STEP_LABELS,
    "fetch_profile": "Fetching profile",
    "fetch_timeline": "Fetching timeline references",
    "rank_references": "Ranking references",
}


@dataclass(frozen=True)
class PipelineProgressEvent:
    step_id: str
    label: str
    status: ProgressStatus
    scope: ProgressScope = "orchestrator"
    parent_id: str | None = None
    purpose: str | None = None

    def as_sse_dict(self) -> dict[str, str | None]:
        payload = asdict(self)
        return {"type": "progress", **payload}


ProgressCallback = Callable[[PipelineProgressEvent], None]
LegacyProgressCallback = Callable[[str, str, str], None]

_progress_cb: ContextVar[ProgressCallback | None] = ContextVar("pipeline_progress", default=None)


def set_progress_callback(cb: ProgressCallback | None) -> None:
    _progress_cb.set(cb)


def reset_progress_callback(token: object) -> None:
    _progress_cb.reset(token)  # type: ignore[arg-type]


def emit(event: PipelineProgressEvent) -> None:
    cb = _progress_cb.get()
    if cb is not None:
        cb(event)


def _default_label(step_id: str, label: str | None) -> str:
    if label:
        return label
    return LEGACY_STEP_LABELS.get(step_id, step_id)


def progress_step(
    step_id: str,
    label: str | None = None,
    *,
    status: ProgressStatus = "active",
    scope: ProgressScope = "orchestrator",
    parent_id: str | None = None,
    purpose: str | None = None,
) -> None:
    emit(
        PipelineProgressEvent(
            step_id=step_id,
            label=_default_label(step_id, label),
            status=status,
            scope=scope,
            parent_id=parent_id,
            purpose=purpose,
        )
    )


def progress_active(
    step_id: str,
    label: str | None = None,
    *,
    scope: ProgressScope = "orchestrator",
    parent_id: str | None = None,
    purpose: str | None = None,
) -> None:
    progress_step(
        step_id,
        label,
        status="active",
        scope=scope,
        parent_id=parent_id,
        purpose=purpose,
    )


def progress_done(
    step_id: str,
    label: str | None = None,
    *,
    scope: ProgressScope = "orchestrator",
    parent_id: str | None = None,
    purpose: str | None = None,
) -> None:
    progress_step(
        step_id,
        label,
        status="done",
        scope=scope,
        parent_id=parent_id,
        purpose=purpose,
    )


def progress_error(step_id: str, message: str, *, scope: ProgressScope = "orchestrator") -> None:
    display = LEGACY_STEP_LABELS.get(step_id, step_id)
    emit(
        PipelineProgressEvent(
            step_id=step_id,
            label=f"{display}: {message}",
            status="error",
            scope=scope,
        )
    )


def adapt_legacy_callback(cb: LegacyProgressCallback) -> ProgressCallback:
    """Bridge old (step_id, label, status) handlers to typed events."""

    def _wrapped(event: PipelineProgressEvent) -> None:
        cb(event.step_id, event.label, event.status)

    return _wrapped


def run_with_progress(cb: ProgressCallback | LegacyProgressCallback, fn: Callable[[], Any]) -> Any:
    wrapped = adapt_legacy_callback(cb) if _callback_arity_is_legacy(cb) else cb
    token = _progress_cb.set(wrapped)
    try:
        progress_active("start")
        progress_done("start")
        return fn()
    finally:
        _progress_cb.reset(token)


def _callback_arity_is_legacy(cb: ProgressCallback | LegacyProgressCallback) -> bool:
    # Legacy handlers accept exactly three positional string args.
    code = getattr(cb, "__code__", None)
    return code is not None and code.co_argcount == 3

"""Full-fidelity step trace: untruncated capture + in-process persistence sink.

This path is INDEPENDENT of NATS. It writes one StepOutputDocument per step at
the step boundary and a PipelineRunDocument header (with ordered step_links) when
the run completes — so the trace is durable even when NATS is OFF. It does NOT
replace the NATS projection (which stays lossy/optional for the live dashboard).
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from app.models.pipeline_run import PipelineRunDocument
from app.models.step_output import StepLink, StepOutputArtifact, StepOutputDocument
from app.pipeline.events.dispatcher import current_run_id
from app.pipeline.events.types import PipelineEvent, _now_iso
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.services.pipeline_run_repository import PipelineRunRepository
from app.services.step_output_repository import StepOutputRepository

logger = logging.getLogger(__name__)


def _full_artifact(ctx: TickRunContext, key: ArtifactKey) -> StepOutputArtifact:
    """Untruncated mirror of capture.py's per-artifact snapshot.

    Unlike capture_artifacts(), the value is ALWAYS the full payload (no 8000-char
    cap, no settings.pipeline_capture_payloads gate). Size is best-effort.
    """
    present = ctx.has_artifact(key)
    if not present:
        return StepOutputArtifact(artifact=key.value, present=False)
    raw = ctx.data.get(key.value)
    try:
        size = len(json.dumps(raw, default=str, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        size = None
    return StepOutputArtifact(artifact=key.value, present=True, size_bytes=size, value=raw)


def capture_artifacts_full(
    ctx: TickRunContext, keys: tuple[ArtifactKey, ...]
) -> list[StepOutputArtifact]:
    return [_full_artifact(ctx, key) for key in keys]


_trace_sink: ContextVar["StepTraceSink | None"] = ContextVar("pipeline_step_trace_sink", default=None)


def set_trace_sink(sink: "StepTraceSink | None"):
    return _trace_sink.set(sink)


def reset_trace_sink(token) -> None:
    _trace_sink.reset(token)


def record_step_trace(*, flat, ctx, result, status, skip_reason, error,
                      started_at, ended_at, duration_ms) -> None:
    """Assemble + emit one StepOutputDocument from full ctx data. No-op if no sink.

    Called from _run_step_with_progress on BOTH the success/skip return path and
    the exception return path; exactly one of those returns executes per step, so
    each step is traced exactly once. Safe to call with sink unset (no-op) — that
    is the property that keeps unit tests calling run_steps directly byte-identical
    (see §7b note).
    """
    sink = _trace_sink.get()
    if sink is None:
        return
    step = flat.step
    doc = StepOutputDocument(
        run_id=current_run_id() or "",      # dispatcher contextvar, bound by run_events (dispatcher.py:90-92)
        account_id=ctx.account_id,
        step_id=flat.id,
        scope="runbook",
        parent_id=flat.parent_id,
        purpose=step.purpose or None,
        status=status,
        skip_reason=skip_reason,
        error=error,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        inputs=capture_artifacts_full(ctx, tuple(step.reads) + tuple(step.reads_optional)),
        outputs=capture_artifacts_full(ctx, tuple(step.writes)),
        result_payload=dict(getattr(result, "payload", {}) or {}),
    )
    sink.on_step(doc)


class StepTraceSink:
    """In-process trace sink. Registered via run_events() so it shares the run
    lifecycle, but the engine calls on_step() directly at each step boundary.

    on_event() is a no-op that satisfies the EventSink protocol — this sink does
    NOT consume the truncated event stream; it works from full ctx data instead.
    """

    def __init__(
        self,
        *,
        run_id: str,
        account_id: str,
        slot: str,
        mode: str,
        niche: str = "",
        started_at: str | None = None,
        step_repo: StepOutputRepository | None = None,
        run_repo: PipelineRunRepository | None = None,
    ) -> None:
        self._steps = step_repo or StepOutputRepository()
        self._runs = run_repo or PipelineRunRepository()
        self._header = PipelineRunDocument(
            run_id=run_id, account_id=account_id, slot=slot, mode=mode,
            niche=niche, status="running", started_at=started_at,
        )
        self._links: list[StepLink] = []
        self._seq = 0

    # EventSink protocol — intentionally a no-op (full capture happens in on_step).
    def on_event(self, event: PipelineEvent) -> None:  # pragma: no cover - interface shim
        return None

    def on_step(self, doc: StepOutputDocument) -> None:
        """Persist ONE step's full trace and record an ordered link. Never raises
        into the pipeline (a trace failure must not fail a post)."""
        self._seq += 1
        doc.seq = self._seq
        try:
            doc_id = self._steps.save(doc)
        except Exception:
            logger.exception("step trace: failed to save step %s/%s", doc.run_id, doc.step_id)
            return
        self._links.append(
            StepLink(
                step_id=doc.step_id, scope=doc.scope, seq=doc.seq,
                status=doc.status, duration_ms=doc.duration_ms, doc_id=doc_id,
            )
        )

    def finalize(self, *, status: str, duration_ms: int | None, ended_at: str | None = None,
                 summary: dict[str, Any] | None = None) -> None:
        """Write the run header with the ordered step_links. Called once in the
        run_account_pipeline finally block."""
        self._header.status = status
        self._header.duration_ms = duration_ms
        self._header.ended_at = ended_at
        self._header.step_links = self._links
        self._header.step_count = len(self._links)
        if summary:
            self._header.summary = summary
        try:
            self._runs.save(self._header)
        except Exception:
            logger.exception("step trace: failed to save run header %s", self._header.run_id)

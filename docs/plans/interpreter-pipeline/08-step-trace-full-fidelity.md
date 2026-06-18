# Task 08 — Full-Fidelity Step Trace (untruncated, NATS-independent)

> **Status:** Ready to implement. Authored cold from verified code; pick up from this folder.
> **Scope:** Backend only — one new model file, one new repository, one new in-process sink, and a ~10-line hook in the runbook engine + `run_account_pipeline`. No frontend in this task.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB; in-process APScheduler).
> **DB reality:** RavenDB has NO multi-doc transactions and the HTTP client has NO If-Match/CAS (`ravendb_http.py:103-110`). This task needs none of that — every write is an independent, idempotent PUT keyed by `{run_id}/{step_id}`.

---

## 1. Why this change

The user requires the **complete** input + output of every pipeline step to be persisted, **untruncated**, for display. Two facts about the current code make this a real change, not a config flip:

1. **The only persistence path today is truncated AND NATS-gated.**
   - `capture_artifacts()` → `_snapshot()` caps every payload at `_MAX_JSON_CHARS = 8000` and only includes a body at all when `settings.pipeline_capture_payloads` is on (`app/pipeline/events/capture.py:17-31`). The truncated snapshots ride inside `PipelineEvent.data` to NATS.
   - The run document is materialized **only** by `ProjectionConsumer`, a durable JetStream consumer that early-returns when NATS is unavailable (`app/pipeline/events/projection_consumer.py:30-34`), started from `lifespan()` at `app/main.py:106-109`. **NATS OFF ⇒ no `PipelineRunDocument` is ever written.**

2. **The run document is a single unbounded doc with nested steps.** `PipelineRunDocument.steps: list[PipelineStepRecord]` holds inputs/outputs **inline** (`app/models/pipeline_run.py:32-44`). Storing full untruncated payloads inline would grow one doc without bound.

**Goal:** persist each step's **complete** typed input + output as its **own** document (`StepOutputDocument`, id `stepoutputs/{run_id}/{step_id}`), and make `PipelineRunDocument` the **one posting-pipeline document** — a run header plus an **ordered list of links** to those step docs. Write both via an **in-process sink at each step boundary**, so the trace persists **even when NATS is OFF**. NATS and the existing `ProjectionConsumer` stay exactly as they are (optional, lossy, for the live dashboard stream); they are not on this path.

This is the explicit user decision: **full fidelity, no truncation, separate-doc-per-step.** The persisted trace is a **passive display artifact** — it never drives execution (the Interpreter walks the spec; see `06`).

---

## 2. Design at a glance

```
                       run_account_pipeline(ctx, account)          [runner.py:139-159]
                       run_id = ctx.forced_run_id or uuid4().hex
   ┌───────────────────────────────────────────────────────────────────────────────┐
   │ run_events(sinks=[NatsPublishSink(), StepTraceSink(run_id, account, slot,mode)])│  ← ADD second sink
   └───────────────────────────────────────────────────────────────────────────────┘
                                   │
   ┌───────────────────────────────┼────────────────────────────────────────────────┐
   │ run_steps → _run_step_with_progress(flat, ctx, deps)   [_runbook_engine.py:42]   │
   │   after step.run(...) succeeds/fails, with ctx + flat IN SCOPE:                  │
   │      record_step_trace(flat, ctx, result, duration_ms, status)  ← ADD ~6 lines   │
   │            │ full untruncated capture of reads+writes from ctx.data              │
   │            ▼                                                                      │
   │      StepTraceSink.on_step(StepOutputDocument)                                   │
   │            ├─► StepOutputRepository.save()  → PUT stepoutputs/{run_id}/{step_id} │
   │            └─► append link to in-memory run header                               │
   └──────────────────────────────────────────────────────────────────────────────────┘
                                   │ on run_completed
                                   ▼
                       PipelineRunRepository.save(run header + ordered step links)
```

**Why a step-boundary hook and not a pure `EventSink`.** An `EventSink` only receives a `PipelineEvent` (`dispatcher.py:42-58`), whose `data["inputs"]/["outputs"]` are the **already-truncated** `capture_artifacts()` output. Full fidelity requires the live `ctx.data` and the step's `StepResult` return value — both in scope **only** inside `_run_step_with_progress`. So the full-capture call lives at the step boundary; `StepTraceSink` is the thing it hands the assembled document to. (`StepTraceSink` is still registered through `run_events` so it shares the run's lifecycle, but it exposes an `on_step()` method the engine calls directly, in addition to the no-op `on_event()` that satisfies the `EventSink` protocol.)

---

## 3. File-by-file plan

| Kind | File | Role (one line) |
|---|---|---|
| **NEW** | `app/models/step_output.py` | `StepOutputDocument` (full payload per step) + `StepOutputArtifact` + `StepLink`; extend `PipelineRunDocument` with `step_links`. |
| **NEW** | `app/services/step_output_repository.py` | `StepOutputRepository.save()/get()/list_for_run()` → RavenDB collection `StepOutputs`, doc id `stepoutputs/{run_id}/{step_id}`. |
| **NEW** | `app/pipeline/events/step_trace.py` | `capture_artifacts_full()` (untruncated) + `StepTraceSink` (in-process; writes step docs, accumulates run header). |
| **CHANGED** | `app/pipeline/_runbook_engine.py` | In `_run_step_with_progress`, after the step runs, call `record_step_trace(...)` (full capture + `sink.on_step(...)`). ~10 lines. |
| **CHANGED** | `app/interval/runner.py` | Build a `StepTraceSink` in `run_account_pipeline`, register it in `run_events(sinks=[...])`, and `sink.finalize(status, duration_ms)` in the `finally`. |
| **REUSED** (verbatim) | `app/models/pipeline_run.py` | `PipelineRunDocument` (run header) — we add ONE field (`step_links`), keep the rest. |
| **REUSED** (verbatim) | `app/services/pipeline_run_repository.py` | `PipelineRunRepository.save()` writes the run header (`put_document(..., model_dump(exclude_none=True), collection="PipelineRuns")`). |
| **REUSED** (read for shape only) | `app/pipeline/events/capture.py` | `capture_artifacts()` is the template; we copy its presence/size logic but **drop the 8000-char cap and the `pipeline_capture_payloads` gate** for the stored doc. |
| **UNTOUCHED** | `app/pipeline/events/projection_consumer.py`, `app/pipeline/events/projection.py`, `app/pipeline/events/sinks.py` | The NATS path is left exactly as-is. This task does not modify or depend on it. |

---

## 4. The model — `app/models/step_output.py` (NEW)

Verified against `app/models/pipeline_run.py:10-48` (the existing run doc) and `capture.py:34-47` (the per-artifact dict shape).

```python
"""Full-fidelity per-step trace documents (untruncated step I/O).

Each pipeline step's COMPLETE input + output is stored as its own RavenDB
document (collection StepOutputs, id stepoutputs/{run_id}/{step_id}). The run
header (PipelineRunDocument) carries an ORDERED list of links to these docs.
Separate-doc-per-step is how we keep full fidelity without an unbounded run doc.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepOutputArtifact(BaseModel):
    """One captured artifact (an input read or an output write) of a step.

    Mirrors the dict shape emitted by capture_artifacts() (capture.py:39-45) but
    `value` is ALWAYS the full untruncated payload (no 8000-char cap, no gate).
    """

    artifact: str                       # ArtifactKey.value, e.g. "timeline_references"
    present: bool
    size_bytes: int | None = None
    value: Any | None = None            # full JSON-able payload; None only if absent


class StepOutputDocument(BaseModel):
    """Complete trace of ONE step execution. Document id: stepoutputs/{run_id}/{step_id}."""

    run_id: str
    account_id: str
    step_id: str                        # dotted flat id, e.g. "summarize_for_compose.analyze_own_posts.rank_own_posts"
    scope: str = "runbook"              # runbook | orchestrator (see §8 for orchestrator phases)
    parent_id: str | None = None
    purpose: str | None = None
    seq: int = 0                        # execution order within the run (1-based)
    status: str = "ok"                  # ok | skipped | error
    skip_reason: str | None = None
    error: dict[str, Any] | None = None # {type, message, traceback} on failure
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    inputs: list[StepOutputArtifact] = Field(default_factory=list)   # full reads + reads_optional
    outputs: list[StepOutputArtifact] = Field(default_factory=list)  # full writes
    result_payload: dict[str, Any] = Field(default_factory=dict)     # StepResult.payload (tool.py:14)

    @staticmethod
    def document_id(run_id: str, step_id: str) -> str:
        return f"stepoutputs/{run_id}/{step_id}"


class StepLink(BaseModel):
    """Ordered pointer from the run header to one StepOutputDocument."""

    step_id: str
    scope: str = "runbook"
    seq: int = 0
    status: str = "ok"
    duration_ms: int | None = None
    doc_id: str                         # stepoutputs/{run_id}/{step_id}
```

### Extension to `app/models/pipeline_run.py` (the "one posting pipeline document")

`PipelineRunDocument` (`pipeline_run.py:32-48`) stays the run header. Add exactly one field; **keep `steps` as-is** (it is still populated by the NATS projection when NATS is on, and our header writer simply leaves it empty when NATS is off — `model_dump(exclude_none=True)` plus a `default_factory=list` means an empty `steps` is harmless).

```python
class PipelineRunDocument(BaseModel):
    run_id: str
    account_id: str
    slot: str
    mode: str = "scheduled"
    niche: str = ""
    status: str = "running"
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    step_count: int = 0
    steps: list[PipelineStepRecord] = Field(default_factory=list)  # UNCHANGED (NATS projection fills this)
    step_links: list[StepLink] = Field(default_factory=list)       # NEW: ordered links to StepOutputDocument
    summary: dict[str, Any] = Field(default_factory=dict)
    ...
```

`StepLink` is imported into `pipeline_run.py` from `step_output.py`. (One-way import only; `step_output.py` imports nothing from `pipeline_run.py`, so no cycle.)

**Definition of Done (slice 4):** `python -c "from app.models.step_output import StepOutputDocument, StepOutputArtifact, StepLink"` succeeds; `StepOutputDocument.document_id('abc', 'load_account_bundle') == 'stepoutputs/abc/load_account_bundle'`; `PipelineRunDocument(...).step_links == []` by default.

---

## 5. The repository — `app/services/step_output_repository.py` (NEW)

Direct mirror of `PipelineRunRepository` (`pipeline_run_repository.py:24-64`), verified against `ravendb_http.put_document()` (`ravendb_http.py:103-110`) and `query()`.

```python
"""Persistence for full-fidelity step output documents (RavenDB collection StepOutputs)."""

from __future__ import annotations

import logging
import re

from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.step_output import StepOutputDocument

logger = logging.getLogger(__name__)

STEP_OUTPUT_COLLECTION = "StepOutputs"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_meta(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class StepOutputRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, doc: StepOutputDocument) -> str:
        doc_id = StepOutputDocument.document_id(doc.run_id, doc.step_id)
        # Unconditional PUT keyed by {run_id}/{step_id} → idempotent: a replay
        # overwrites the same doc, never duplicates (no CAS needed). See Decision Defense.
        self.client.put_document(
            doc_id, doc.model_dump(exclude_none=True), collection=STEP_OUTPUT_COLLECTION
        )
        return doc_id

    def get(self, run_id: str, step_id: str) -> StepOutputDocument | None:
        raw = self.client.get_document(StepOutputDocument.document_id(run_id, step_id))
        if raw is None:
            return None
        try:
            return StepOutputDocument.model_validate(_strip_meta(raw))
        except Exception as exc:
            logger.debug("StepOutputs get invalid doc %s/%s: %s", run_id, step_id, exc)
            return None

    def list_for_run(self, run_id: str, *, limit: int = 200) -> list[StepOutputDocument]:
        rid = _safe_rql_string(run_id)
        if not rid:
            return []
        cap = max(1, min(int(limit), 500))
        rql = f'from {STEP_OUTPUT_COLLECTION} where run_id == "{rid}" order by seq limit {cap}'
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("StepOutputs query failed: %s", exc)
            return []
        out: list[StepOutputDocument] = []
        for raw in rows:
            try:
                out.append(StepOutputDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("StepOutputs skip invalid row: %s", exc)
        return out
```

> `query()` and `put_document()` are confirmed present on `RavenDBHttpClient` (used by `PipelineRunRepository` and `ravendb_http.py:103`). `order by seq` requires a default index on `seq`; RavenDB auto-creates one on first query — acceptable for a low-volume trace collection. Consumers that prefer to avoid index latency can ignore `list_for_run` and follow `PipelineRunDocument.step_links` (already ordered) via `get()` per link.

**Definition of Done (slice 5):** with the stack up, `StepOutputRepository().save(doc)` returns `stepoutputs/{run_id}/{step_id}`; `get(run_id, step_id)` round-trips; the doc appears in the `StepOutputs` collection in RavenDB Studio.

---

## 6. The full-fidelity capture + in-process sink — `app/pipeline/events/step_trace.py` (NEW)

Two pieces: an **untruncated** capture function (copied from `capture.py` with the cap removed) and the `StepTraceSink` that persists step docs and accumulates the run header. (§7a **appends** the contextvar + `record_step_trace`/`set_trace_sink`/`reset_trace_sink` machinery and two more imports — `from contextvars import ContextVar` and `from app.pipeline.events.dispatcher import current_run_id` — to this same file; the imports below are the slice-6 set, not the final set.)

```python
"""Full-fidelity step trace: untruncated capture + in-process persistence sink.

This path is INDEPENDENT of NATS. It writes one StepOutputDocument per step at
the step boundary and a PipelineRunDocument header (with ordered step_links) when
the run completes — so the trace is durable even when NATS is OFF. It does NOT
replace the NATS projection (which stays lossy/optional for the live dashboard).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.pipeline_run import PipelineRunDocument
from app.models.step_output import StepLink, StepOutputArtifact, StepOutputDocument
from app.pipeline.events.types import PipelineEvent  # for EventSink protocol compatibility
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
```

> **Note (future-only) externalization for giant payloads.** `value` stores the full payload **inline** by default — correct for current artifacts (the largest, `timeline_references`, is a bounded list of tweet rows). If a future artifact is genuinely huge, externalize *that* artifact: store it as a RavenDB **attachment** on the step doc (or a blob ref) and set `value=None` with a `ref` field. This is a per-artifact escape hatch; **do not** build it now (simplicity-first). Default = full inline.

**Definition of Done (slice 6):** unit-constructible without NATS — `StepTraceSink(run_id=..., account_id=..., slot=..., mode=...)`; `capture_artifacts_full(ctx, (ArtifactKey.TIMELINE_REFERENCES,))` returns one `StepOutputArtifact` whose `value` equals `ctx.data["timeline_references"]` with no truncation marker.

---

## 7. The hook — `_runbook_engine.py` + `runner.py` (CHANGED)

### 7a. Step boundary hook (`app/pipeline/_runbook_engine.py:42-148`)

`_run_step_with_progress` already has `flat`, `ctx`, `result`, `duration_ms`, and the start time in scope. Add a single helper call after the status branch is determined. The sink reference is fetched from a module-level contextvar set by `run_account_pipeline` (parallel to how `_dispatcher` is bound in `dispatcher.py:61-63`) so the engine does not change its signature.

`_runbook_engine.py` gains exactly two new imports at module top: `from app.pipeline.events.step_trace import record_step_trace` and `from app.pipeline.events.types import _now_iso`. This is a one-way import — `step_trace.py` imports nothing from `_runbook_engine.py` (it imports the models, repos, `dispatcher.current_run_id`, `types.artifacts`, `types.context`), so there is **no cycle**.

Add to `step_trace.py` (`run_id` is read from the dispatcher contextvar via `current_run_id()`, which `run_events` already binds — see §7c for why this, not a `ctx.run_id` field):

```python
from contextvars import ContextVar

from app.pipeline.events.dispatcher import current_run_id

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
```

> `step = flat.step` (a `Step`, `flow.py:18-33`) exposes `reads`/`writes` (`tuple[ArtifactKey, ...]`) and `reads_optional` (`frozenset[ArtifactKey]`); `tuple(step.reads_optional)` is correct. `flat.id` is the dotted leaf id and `flat.parent_id` the optional parent (`FlatStep`, `flow.py:94-100`). `result.payload` is the `StepResult.payload` dict (`tool.py:14`); on the exception path `result` is the freshly built `StepResult(ok=False, errors=[...])` so `getattr(result, "payload", {})` yields `{}` — no `AttributeError`.

**Insertion into `_run_step_with_progress`** (current line numbers, verified against `_runbook_engine.py:42-148`). Two helper edits and two call sites — one per `return`:

1. **At step start** (after `started = time.monotonic()`, `:63`): also capture `started_iso = _now_iso()` (import `_now_iso` from `app.pipeline.events.types`). Keep `started` (the monotonic) for the existing `duration_ms` math; `started_iso`/`ended_iso` are only for the trace doc's ISO timestamps.

2. **Exception path** (`:66-88`): hoist the error dict so it can be shared. Today the dict is an inline literal inside the `emit_step_failed(...)` call (`:73-77`) — there is nothing to "reuse" as written. Assign it to a local first, pass that local to `emit_step_failed`, then to `record_step_trace`:
   ```python
   except Exception as exc:
       logger.exception("runbook step %s failed", flat.id)
       err = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
       progress_error(flat.id, "step_exception", scope="runbook")
       emit_step_failed(flat.id, scope="runbook", parent_id=flat.parent_id,
                        error=err, duration_ms=int((time.monotonic() - started) * 1000))
       entry = {...}                                  # unchanged
       record_step_trace(flat=flat, ctx=ctx, result=StepResult(ok=False, errors=[str(exc)]),
                          status="error", skip_reason=None, error=err,
                          started_at=started_iso, ended_at=_now_iso(),
                          duration_ms=int((time.monotonic() - started) * 1000))
       return StepResult(ok=False, errors=[str(exc)]), entry
   ```

3. **Success/skip path** (`:107-146`): after the three progress/emit branches and just before `return result, entry` (`:148`), add ONE call, deriving `status` from the result:
   ```python
   status = "skipped" if result.skipped else ("ok" if result.ok else "error")
   record_step_trace(flat=flat, ctx=ctx, result=result, status=status,
                      skip_reason=result.skip_reason, error=None,
                      started_at=started_iso, ended_at=_now_iso(), duration_ms=duration_ms)
   return result, entry
   ```

### 7b. Sink registration (`app/interval/runner.py:139-159`)

```python
def run_account_pipeline(ctx: TickContext, account: AccountDocument) -> dict[str, Any]:
    run_id = ctx.forced_run_id or uuid4().hex
    started = time.monotonic()
    started_iso = _now_iso()                                            # ADD
    trace = StepTraceSink(                                              # ADD
        run_id=run_id, account_id=account.account_id, slot=ctx.slot,
        mode=ctx.mode, niche=account.category or "", started_at=started_iso,
    )
    token = set_trace_sink(trace)                                       # ADD (binds contextvar)
    with run_events(
        run_id=run_id, account_id=account.account_id, slot=ctx.slot, mode=ctx.mode,
        sinks=[NatsPublishSink(), trace],            # ADD trace as a second sink (on_event no-op)
    ):
        emit_run_started(niche=account.category or "")
        status = "error"
        try:
            out = _run_account_pipeline(ctx, account)
            status = _run_status_from_out(out)
            return out
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            emit_run_completed(status=status, duration_ms=duration_ms)
            trace.finalize(status=status, duration_ms=duration_ms, ended_at=_now_iso())  # ADD
            reset_trace_sink(token)                                     # ADD
```

`_now_iso` reuses the existing helper in `events/types.py:25-26` (`from app.pipeline.events.types import _now_iso`); the same import is used in `_runbook_engine.py` §7a for `started_iso`/`ended_iso`. (Alternatively `datetime.now(timezone.utc).isoformat()` — `runner.py` already imports `datetime, timezone`.)

> **Ordering of the contextvar binding (verified safe).** `set_trace_sink(trace)` runs **before** `with run_events(...)` and `reset_trace_sink(token)` runs in the **finally** after `run_events` exits — so the sink is live for the whole step walk and torn down with the run. The order relative to `run_events` does not matter for correctness (both are independent contextvars), but binding the sink first means a step that somehow runs during `run_events` setup is still captured.

> **No-op when the sink is unset (keeps every other call site byte-identical).** Many unit tests call `run_steps(...)` directly **without** going through `run_account_pipeline` (e.g. `tests/unit/test_pipeline_runbook.py`), so the `_trace_sink` contextvar is at its `default=None`. `record_step_trace` returns immediately when `sink is None` (§7a) and `capture_artifacts_full` is never called, so those runs are byte-identical to today — no `StepOutputDocument` written, no behavior change. This is the property doc 13 §2 relies on for "08 is additive, green on its own."

**Definition of Done (slice 7):** with **NATS OFF** (`nats_enabled=false`), one force-post run produces N `StepOutputDocument`s in `StepOutputs` (one per flattened runbook leaf — 8 today, see `runbooks/post_tick.py`) **and** one `PipelineRunDocument` whose `step_links` is ordered by `seq` and whose `doc_id`s resolve via `StepOutputRepository.get()`. Each step doc's `inputs`/`outputs` contain the **full** artifact JSON (verify a `timeline_references` payload exceeding 8000 chars is stored whole, no `... [truncated]` marker).

### 7c. `run_id` sourcing — `current_run_id()`, not a `ctx.run_id` field (coordination with doc 07)

This task reads `run_id` from the **dispatcher contextvar** via `current_run_id()` (`dispatcher.py:90-92`), bound by `run_events` for the whole run. It deliberately does **not** read a `TickRunContext.run_id` field, because:

- **`TickRunContext` has no `run_id` field today** (`context.py:16-21`: only `account_id`/`slot`/`mode`/`niche`/`data`). Doc 13 §2 sequences **08 before 06/07**, and 08 must compile + run green on its own; depending on a field that doc 07 §6 adds later would make 08 fail in its own window.
- **Doc 07 §6 adds `run_id: str = ""` to `TickRunContext` and sets it from `current_run_id()`.** That field is for doc 07's `CostMeter` and `publish_post` attribution — it is sourced from the *same* dispatcher value, so it can never disagree with what this trace reads. After 07 lands, **this trace stays on `current_run_id()`** (no edit needed); both paths key off the one authoritative dispatcher `run_id`, exactly as doc 07 §6's Decision Defense argues ("read `run_id` from the dispatcher, don't pass it down a new param chain"). No reconciliation, no follow-up edit.

### 7d. Coexisting with doc 07's `wrappers` edit to the *same* function (forward-compat)

Doc 07 §3 also edits `_run_step_with_progress` — it adds a `wrappers: Sequence[StepWrapper] = ()` param and changes the single call `step.run(ctx, deps)` (`:65`) to `run_fn(ctx, deps)`, where `run_fn` is `step.run` after the engine-injected cost+guardian wrappers are applied. Because **08 lands first** (doc 13 §2), the doc-07 implementer merges *into* the already-trace-hooked function. The combined shape is unambiguous, and these two answers are binding so there is no integration guesswork:

1. **The trace captures the WRAPPED result.** `record_step_trace` runs on whatever `result` the (possibly wrapped) `run_fn` returned — i.e. the same object `run_steps` acts on. The cost meter (`record_after`) drains `_step_cost_usd` from `ctx.data` *inside* the wrapper, so by the time `record_step_trace` reads `ctx.data`, the reserved `_step_cost_usd` key is already popped and never appears in any artifact (it is not an `ArtifactKey`, so `capture_artifacts_full` — which iterates only `step.reads/writes/reads_optional` — never sees it regardless).
2. **A `CostCeilingExceeded` (or any wrapper raise) is traced as `status="error"`.** It propagates out of `run_fn` into the existing `except Exception` block (`:66-88`), which is exactly the path §7a hooks with `status="error"` and the hoisted `err` dict. So the blocked step gets a `StepOutputDocument` with `status="error"` and the exception details — matching doc 07 §4.3 ("the trace records exactly which step was blocked") and doc 13's cost-ceiling spot-check. No special-casing needed; the wrapper raise rides the same error return path this task already traces.

Net: 08's hook and 07's wrappers touch the same function but compose cleanly — 07 wraps `step.run`→`run_fn` and passes `wrappers` through; 08's `record_step_trace` calls sit on the two `return` paths unchanged.

---

## 8. Scope boundary: SENSE steps now, ACT phases via doc 06

The typed engine currently runs **only** the SENSE/reference runbook (`run_reference_phase` → `run_steps(POST_TICK_REFERENCE_STEPS, ...)`, `reference_phase.py:85`). The DECIDE→ACT tail (compose / guardian / select / publish) is hand-written imperative code in `runner.py::_run_account_pipeline` and is **not** a typed step yet (the load-bearing truth; crux of doc **06**).

**Consequence for this task:** the step-boundary hook in §7a captures **every typed step the engine runs**. Today that is the 8 SENSE leaves. When doc **06** turns the ACT tail into typed steps (notably the coarse `compose_until_safe` and `publish_post` tools running through `run_steps`), those steps flow through the **same** `_run_step_with_progress` hook and are captured **automatically** — no change to this task. The `scope` field on `StepOutputDocument` is set to `"runbook"` here; doc 06 may emit ACT steps under the same engine, so they too will be `"runbook"` scope. **This task does not retrofit the current imperative orchestrator phases** (`load_account`, `post_lock`, `compose`, `safety`, `publish`) into typed steps — that is doc 06's job. They remain visible only via the existing progress/NATS stream until then.

This keeps the slice surgical: we add the persistence seam once, at the one place every typed step already passes through.

> **Step-count expectation across the sequence (so a verifier does not mis-flag).** Doc 13 §2 sequences **08 at step 6, before 06/07 (steps 7–8)**. In the 08-only window a force-post writes **exactly 8** `StepOutputDocument`s (the SENSE leaves) and a `PipelineRunDocument` whose `step_links` has 8 entries — the compose/safety/publish phases run as imperative orchestrator code (`runner.py:302-438`, `scope="orchestrator"`, emitted via `_orch_active`/`_orch_done`, which do **not** pass through `_run_step_with_progress`) and are therefore **legitimately absent** from the trace. This is correct, not a bug: a frontend `RunTraceViewer` check (doc 11 §5) run in this window will show an 8-row chain with no compose/publish rows — do not flag the missing ACT rows. After 06/07 land, `compose_until_safe` + `publish_post` flow through the same hook and the chain becomes **10 rows** (doc 13 §4.B B5) with **no edit to this task**. The acceptance in §10 below is written for the 8-leaf, 08-only state.

**Why a step-boundary hook instead of a pure `EventSink` that folds events (like `ProjectionConsumer`)?**
The event payloads are deliberately truncated for the wire (`capture.py:29-31`, 8000-char cap, gated on `pipeline_capture_payloads`). A sink that consumes events can never recover full fidelity — the data is already gone. The full payload exists only in `ctx.data` at the instant the step finishes, which is exactly where `_run_step_with_progress` sits. Hooking there is the *only* place that can satisfy "untruncated" without re-plumbing the entire event envelope to carry megabytes (which would also bloat NATS). The contextvar binding mirrors the existing `_dispatcher` pattern (`dispatcher.py:61-81`), so no engine signature changes.

**Why separate-doc-per-step instead of fatter nested `PipelineRunDocument.steps`?**
The user wants full untruncated I/O. Inlining that into one run doc grows it unbounded (RavenDB documents are meant to be bounded; large docs hurt load/serialize/index). One doc per step keeps each write small and the run header tiny (just ordered links). This is the standard "index doc + detail docs" RavenDB shape. The header remains the single "posting pipeline document" the user asked for — it just *links* to the details rather than embedding them.

**Why no CAS / If-Match, given replay can re-run a step?**
The doc id is deterministic: `stepoutputs/{run_id}/{step_id}`. A replay (e.g. the NATS projection re-processes, or a manual re-run with the same `forced_run_id`) overwrites the *same* document with identical content — idempotent by construction. `run_id` is `uuid4().hex` per run (or an explicit `forced_run_id`), so distinct runs never collide. RavenDB has no multi-doc transaction and `put_document` has no If-Match (`ravendb_http.py:103-110`); we need neither, because there is no read-modify-write race — each step writes its own key exactly once per run. The run header is written **once** at `finalize()`, after all step docs exist, so there is no partial-link window during the run (a crash mid-run simply leaves orphan step docs with no header, which `list_for_run` can still recover).

**Why keep `PipelineRunDocument.steps` (the NATS-projected nested list) alongside `step_links`?**
Removing it would break the existing `ProjectionConsumer`/`build_run_document` fold (`projection.py:88`) and the fleet/dashboard queries that read `steps`. The two coexist cleanly: when NATS is ON, the projection fills `steps` (lossy, real-time) and our sink fills `step_links` (full, durable); when NATS is OFF, `steps` is empty and `step_links` is authoritative. `model_dump(exclude_none=True)` keeps empties out of the wire. Surgical: one new field, zero deletions.

**Why does `StepTraceSink.on_step` swallow exceptions?**
The trace is a **passive display artifact** (settled architecture). A RavenDB hiccup while writing a trace doc must never fail a real post. Both `on_step` and `finalize` log-and-continue, exactly like `NatsPublishSink.on_event` (`sinks.py:41-47`).

**Why is this independent of the `ProjectionConsumer` lifespan startup?**
`ProjectionConsumer.start()` early-returns when NATS is down (`projection_consumer.py:32-34`), and it is the *only* writer of `PipelineRunDocument` today. The user explicitly requires the trace to persist with NATS OFF. Our sink runs **in-process, inside the tick thread**, with no NATS dependency, so the trace is written regardless of NATS or the consumer task.

---

## 10. Per-slice Definition of Done (rollup) & verification

Implementation order: **4 (model) → 5 (repo) → 6 (sink) → 7 (hook+wire)**. Slices 4–6 compile independently; slice 7 wires them in.

```bash
cd SocialMediaAutonomousAgents/backend
python -m py_compile \
  app/models/step_output.py app/models/pipeline_run.py \
  app/services/step_output_repository.py \
  app/pipeline/events/step_trace.py \
  app/pipeline/_runbook_engine.py app/interval/runner.py
```

End-to-end (the load-bearing acceptance — **run with NATS OFF**; this is the **08-only window**, before 06/07):
1. Set `nats_enabled=false` (or stop NATS). Trigger one force-post for `JohnJames_News`.
2. In RavenDB Studio, confirm collection **`StepOutputs`** has **exactly 8** docs for that `run_id` — one per flattened SENSE leaf (ids `stepoutputs/{run_id}/load_account_bundle`, `.../fetch_search_references`, `.../collect_external_references`, `.../fetch_own_post_history`, `.../summarize_for_compose.analyze_external_references.rank_external_references`, `.../summarize_for_compose.analyze_external_references.brief_external_references`, `.../summarize_for_compose.analyze_own_posts.rank_own_posts`, `.../summarize_for_compose.analyze_own_posts.brief_own_posts`), each with full `inputs`/`outputs`. The compose/safety/publish phases are imperative orchestrator code in this window (§8) and are correctly **absent** — do not expect `compose_until_safe`/`publish_post` docs until 06/07 land.
3. Confirm collection **`PipelineRuns`** has `pipelineruns/{run_id}` with `step_links` ordered by `seq` (8 entries), `step_count == len(step_links) == 8`, and `steps == []` (NATS off ⇒ projection didn't run).
4. Pick the largest step (`collect_external_references`, whose output `timeline_references` is the reference pool) and confirm its output `value` is the **complete** JSON with **no** `... [truncated, N chars total]` marker. (`fetch_search_references` → `search_references` is also large.)
5. Turn NATS back ON, repeat: `step_links` is still full and durable; `steps` is now additionally populated by the projection. Both present, neither corrupted.

**Grep guard (should return nothing — the trace path must not reuse the truncating capture):**
```bash
grep -rn "capture_artifacts(" app/pipeline/events/step_trace.py   # must be EMPTY; use capture_artifacts_full
```

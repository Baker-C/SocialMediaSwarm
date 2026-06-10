# Task 6: runbook-engine

## Section 1 – Task Overview

### Goal

Update `app/pipeline/_runbook_engine.py` so `run_steps` accepts **`Sequence[Step]`**, flattens parallel/chain composites via `flatten_steps`, and emits **enriched step log entries** (reads, writes, parent_id).

### Gathered context

Engine today iterates `(step_id, fn)` tuples:

```33:90:SocialMediaAutonomousAgents/backend/app/pipeline/_runbook_engine.py
def run_steps(
    steps: Sequence[tuple[str, StepFn]],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
) -> RunbookResult:
    log: list[dict] = []
    outcomes = PipelineOutcomeRepository()
    for step_id, fn in steps:
        try:
            result = fn(ctx, deps)
        except Exception as exc:
            logger.exception("runbook step %s failed", step_id)
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                ...
            )
        # ... StepResult normalization, skip/error outcomes, stop_on_fail ...
    return RunbookResult(ctx, log)
```

Callers:

```38:38:SocialMediaAutonomousAgents/backend/app/pipeline/runbook.py
    return run_steps(POST_TICK_REFERENCE_STEPS, ctx, services)
```

```85:85:SocialMediaAutonomousAgents/backend/app/interval/reference_phase.py
    runbook_result = run_steps(POST_TICK_REFERENCE_STEPS, run_ctx, deps)
```

`RunbookResult.reference_context()` reads four artifact keys—unchanged.

### Dependencies

- **Task 2** (`flatten_steps`, `FlatStep`, `Step`)
- **Task 7** (runbook supplies `Sequence[Step]`)

### What it affects

- `RunbookResult.steps` dicts gain `reads`, `writes`, `parent_id` fields.
- `phase=f"runbook:{step_id}"` strings use dotted flattened IDs (e.g. `runbook:summarize_for_compose.external_reference_analysis.rank_external_references`).
- **No** artifact validation in engine—validation stays in `set_artifact` (locked decision).

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

1. Change signature to `run_steps(steps: Sequence[Step], ...)`.
2. At start: `flat = flatten_steps(steps)`.
3. Loop `for entry in flat:` call `entry.step.run(ctx, deps)`.
4. Log `id=entry.id`, `parent_id=entry.parent_id`, `reads=[k.value for k in entry.step.reads]`, `writes=[...]`.
5. Keep exception handling, `StepResult` coercion, `stop_on_fail`, and `PipelineOutcomeRepository` behavior.

### b. Before Panel

```1:90:SocialMediaAutonomousAgents/backend/app/pipeline/_runbook_engine.py
"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)

StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]


class RunbookResult:
    def __init__(self, ctx: TickRunContext, steps: list[dict]) -> None:
        self.ctx = ctx
        self.steps = steps
        self.ok = all(s.get("ok", False) or s.get("skipped") for s in steps)

    def reference_context(self) -> dict:
        return {
            "timeline": self.ctx.get("timeline_analysis"),
            "own_posts": self.ctx.get("own_posts_analysis"),
            "timeline_ranked": self.ctx.get("timeline_ranked"),
            "own_posts_ranked": self.ctx.get("own_posts_ranked"),
        }


def run_steps(
    steps: Sequencetuple[str, StepFn]],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
) -> RunbookResult:
    log: list[dict] = []
    outcomes = PipelineOutcomeRepository()
    for step_id, fn in steps:
        try:
            result = fn(ctx, deps)
        except Exception as exc:
            logger.exception("runbook step %s failed", step_id)
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason="step_exception",
                details={"error": str(exc)},
            )
            entry = {"id": step_id, "ok": False, "error": str(exc)}
            log.append(entry)
            if stop_on_fail:
                break
            continue

        if not isinstance(result, StepResult):
            result = StepResult(ok=True, payload={"value": result})

        entry = {
            "id": step_id,
            "ok": result.ok,
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "errors": result.errors,
        }
        log.append(entry)
        if result.skipped:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="skipped",
                reason=result.skip_reason,
            )
        elif not result.ok:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason=result.skip_reason or "step_failed",
                details={"errors": list(result.errors or [])},
            )

        if stop_on_fail and not result.ok and not result.skipped:
            break

    return RunbookResult(ctx, log)
```

### c. After Panel

```python
"""Runbook execution (internal — not part of the public import surface)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import Step, flatten_steps  # NEW: Step graph support
from app.pipeline.types.tool import StepResult
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)


class RunbookResult:
    def __init__(self, ctx: TickRunContext, steps: list[dict]) -> None:
        self.ctx = ctx
        self.steps = steps
        self.ok = all(s.get("ok", False) or s.get("skipped") for s in steps)

    def reference_context(self) -> dict:
        # Unchanged — compose/interval still read string keys from ctx.data
        return {
            "timeline": self.ctx.get("timeline_analysis"),
            "own_posts": self.ctx.get("own_posts_analysis"),
            "timeline_ranked": self.ctx.get("timeline_ranked"),
            "own_posts_ranked": self.ctx.get("own_posts_ranked"),
        }


def run_steps(
    steps: Sequence[Step],  # CHANGED: accept Step records, not (id, fn) tuples
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
) -> RunbookResult:
    log: list[dict] = []
    outcomes = PipelineOutcomeRepository()
    flat = flatten_steps(steps)  # NEW: expand parallel/chain to leaf steps with dotted IDs

    for flat_entry in flat:
        step_id = flat_entry.id
        fn = flat_entry.step.run
        try:
            result = fn(ctx, deps)
        except Exception as exc:
            logger.exception("runbook step %s failed", step_id)
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason="step_exception",
                details={"error": str(exc)},
            )
            entry = {
                "id": step_id,
                "ok": False,
                "error": str(exc),
                "parent_id": flat_entry.parent_id,  # NEW: trace nested block
                "reads": [k.value for k in flat_entry.step.reads],
                "writes": [k.value for k in flat_entry.step.writes],
            }
            log.append(entry)
            if stop_on_fail:
                break
            continue

        if not isinstance(result, StepResult):
            result = StepResult(ok=True, payload={"value": result})

        entry = {
            "id": step_id,
            "ok": result.ok,
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "errors": result.errors,
            "parent_id": flat_entry.parent_id,  # NEW
            "reads": [k.value for k in flat_entry.step.reads],  # NEW: artifact I/O audit
            "writes": [k.value for k in flat_entry.step.writes],  # NEW
        }
        log.append(entry)
        if result.skipped:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="skipped",
                reason=result.skip_reason,
            )
        elif not result.ok:
            outcomes.append(
                account_id=ctx.account_id,
                phase=f"runbook:{step_id}",
                status="error",
                reason=result.skip_reason or "step_failed",
                details={"errors": list(result.errors or [])},
            )

        if stop_on_fail and not result.ok and not result.skipped:
            break

    return RunbookResult(ctx, log)
```

### d. Written explanation connecting changes to broader picture

The engine stays a **simple linear executor**—composites are syntactic sugar expanded before the loop. Enriched logs connect operational traces to artifact flow without adding a validation layer (already handled at every `set_artifact`). Dotted IDs align observability with the declared runbook tree from task 7.

---

## Section 3 – Decision Defense

### Chosen path: flatten-then-run

| Alternative | Why not chosen |
|-------------|----------------|
| **Engine interprets composites dynamically** | Duplicates logic already in `flow.py`; harder to test. |
| **Dual API (tuples + Step)** | Confusing; full migration to `Step` only. |
| **Validate reads/writes at engine** | Redundant with strict `set_artifact`; `require_artifact` fails in step body. |

### Composite steps never logged as single opaque entries

Only **leaf** steps produce outcomes and `RunbookResult.steps` rows—matches operator mental model (“rank_external_references ran”), not “summarize_for_compose ran once”.

### `reference_context()` unchanged

Interval/compose migration not required; ctx key strings locked.

### Frontend

**N/A** — internal engine. Force-post SSE remains on separate step IDs (`force_post_progress.py`).

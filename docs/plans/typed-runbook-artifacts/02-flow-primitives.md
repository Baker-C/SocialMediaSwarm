# Task 2: flow-primitives

## Section 1 – Task Overview

### Goal

Add `app/pipeline/types/flow.py` with **`Step` records**, **`parallel()` / `chain()` composites**, and **`flatten_steps()`** so the runbook can declare artifact I/O and nested structure without hiding rank→brief sequencing inside subagent modules.

### Gathered context

The runbook today is a flat tuple of `(step_id, callable)`:

```18:27:SocialMediaAutonomousAgents/backend/app/pipeline/runbooks/post_tick.py
# The runbook — read top to bottom; this is the source of truth for step order.
POST_TICK_REFERENCE_STEPS: tuple[tuple[str, StepFn], ...] = (
    ("profile", steps.profile),
    ("timeline_pool", steps.timeline_pool),
    ("search_pool", steps.search_pool),
    ("merge_reference_pools", steps.merge_reference_pools),
    ("own_posts_pool", steps.own_posts_pool),
    ("timeline_analysis", timeline.run),
    ("own_posts_analysis", own_posts.run),
)
```

The engine accepts the same shape:

```33:42:SocialMediaAutonomousAgents/backend/app/pipeline/_runbook_engine.py
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
```

Two opaque steps (`timeline_analysis`, `own_posts_analysis`) each perform fetch-fallback, rank, enrich, and LLM brief internally (`subagents/timeline.py` lines 21–70, `subagents/own_posts.py` lines 20–69). Parallelism (timeline fetch vs search fetch; external vs own-post analysis) is **not visible** in the runbook file.

Target runbook structure (from parent plan):

```
load_account_bundle
parallel(fetch_timeline_references, fetch_search_references)  → fetch_external_references
merge_external_references
fetch_own_post_history
parallel(
  chain(rank_external_references, brief_external_references),
  chain(rank_own_posts, brief_own_posts),
) → summarize_for_compose
```

### Location in project

| Path | Role |
|------|------|
| `app/pipeline/types/flow.py` | **New** — Step, composites, flattening |
| `app/pipeline/types/__init__.py` | Export `Step`, `parallel`, `chain`, `flatten_steps`, `FlatStep` |
| `app/pipeline/_runbook_engine.py` | Task 6 — consumes flattened steps |
| `app/pipeline/runbooks/post_tick.py` | Task 7 — declares `Sequence[Step]` |

### What it affects

- Replaces tuple-based runbook definition with typed `Step` graph.
- Logging step IDs become dotted for nested children (e.g. `summarize_for_compose.external_reference_analysis.rank_external_references`).
- `test_pipeline_runbook.py` must stop unpacking `(name, fn)` tuples directly (task 8).

### Related changes / dependencies

- **Depends on task 1**: `Step.reads` / `writes` use `ArtifactKey`.
- **Depends on task 5**: leaf step callables must exist before runbook rewrite.
- **Locked decision**: expanded rank+brief steps run **sequentially within each branch** via `chain()`, not parallel rank+brief.

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

1. **`Step` dataclass** — `id`, `run`, `reads`, `writes`, `reads_optional`, `purpose`, optional `children`, `composite_kind`.
2. **`parallel(*steps, id=..., purpose=...)`** — groups siblings; execution runs children sequentially in v1 (true async fetch is follow-up); aggregates I/O metadata from children.
3. **`chain(*steps, id=..., purpose=...)`** — ordered sub-pipeline for rank→brief; deduplicates `reads` while preserving order.
4. **`flatten_steps(steps) -> list[FlatStep]`** — expands composites to leaf steps with dotted IDs for engine logging.
5. **`artifact_graph_mermaid(steps)`** — doc/test helper generating flowchart from declared reads/writes.

### b. Before Panel

**(new file)**

No flow primitives exist. Step typing is duplicated:

```16:16:SocialMediaAutonomousAgents/backend/app/pipeline/runbooks/post_tick.py
StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]
```

```15:15:SocialMediaAutonomousAgents/backend/app/pipeline/_runbook_engine.py
StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]
```

### c. After Panel

```python
"""Runbook flow primitives: Step records, parallel/chain composites, flattening."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]
CompositeKind = Literal["leaf", "parallel", "chain"]


@dataclass(frozen=True)
class Step:
    """One runbook step with declared artifact I/O for dataflow visibility."""

    id: str
    run: StepFn
    reads: tuple[ArtifactKey, ...] = ()
    writes: tuple[ArtifactKey, ...] = ()
    reads_optional: frozenset[ArtifactKey] = field(default_factory=frozenset)
    purpose: str = ""
    children: tuple[Step, ...] = ()  # populated for parallel/chain composites
    composite_kind: CompositeKind = "leaf"

    @property
    def is_composite(self) -> bool:
        return self.composite_kind != "leaf"


def _run_parallel(step: Step) -> StepFn:
    """Composite runner: sequential child execution in v1 (async fetch is follow-up)."""

    def _run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
        last: StepResult = StepResult(ok=True)
        for child in step.children:
            last = child.run(ctx, deps)
            if not last.ok and not last.skipped:
                return last  # stop_on_fail honored at leaf level
        return last

    return _run


def _run_chain(step: Step) -> StepFn:
    """Same execution semantics as parallel; composite_kind distinguishes intent in docs/graph."""

    def _run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
        last: StepResult = StepResult(ok=True)
        for child in step.children:
            last = child.run(ctx, deps)
            if not last.ok and not last.skipped:
                return last
        return last

    return _run


def parallel(*steps: Step, id: str, purpose: str = "") -> Step:
    """Group steps under one logical block; flatten_steps emits parent.child IDs for logs."""
    reads: set[ArtifactKey] = set()
    writes: set[ArtifactKey] = set()
    optional: set[ArtifactKey] = set()
    for s in steps:
        reads.update(s.reads)
        writes.update(s.writes)
        optional.update(s.reads_optional)
    inner = Step(id=id, run=lambda _c, _d: StepResult(ok=True), children=steps)
    return Step(
        id=id,
        run=_run_parallel(Step(id=id, run=lambda _c, _d: StepResult(ok=True), children=steps)),
        reads=tuple(reads),
        writes=tuple(writes),
        reads_optional=frozenset(optional),
        purpose=purpose or f"Parallel block: {', '.join(s.id for s in steps)}",
        children=steps,
        composite_kind="parallel",
    )


def chain(*steps: Step, id: str, purpose: str = "") -> Step:
    """Sequential sub-pipeline — rank then brief within one analysis branch."""
    reads: list[ArtifactKey] = []
    writes: list[ArtifactKey] = []
    optional: set[ArtifactKey] = set()
    seen_reads: set[ArtifactKey] = set()
    for s in steps:
        for r in s.reads:
            if r not in seen_reads:
                reads.append(r)
                seen_reads.add(r)
        writes.extend(s.writes)
        optional.update(s.reads_optional)
    return Step(
        id=id,
        run=_run_chain(Step(id=id, run=lambda _c, _d: StepResult(ok=True), children=steps)),
        reads=tuple(reads),
        writes=tuple(writes),
        reads_optional=frozenset(optional),
        purpose=purpose or " → ".join(s.id for s in steps),
        children=steps,
        composite_kind="chain",
    )


@dataclass(frozen=True)
class FlatStep:
    """Leaf step with full dotted id for PipelineOutcomeRepository phases."""

    id: str
    step: Step
    parent_id: str | None = None


def flatten_steps(steps: Sequence[Step], *, parent_id: str | None = None) -> list[FlatStep]:
    """Expand parallel/chain composites into executable leaf steps with dotted IDs."""
    out: list[FlatStep] = []
    for step in steps:
        if step.is_composite:
            prefix = f"{parent_id}.{step.id}" if parent_id else step.id
            for child in step.children:
                out.extend(_flatten_one(child, prefix))
        else:
            full_id = f"{parent_id}.{step.id}" if parent_id else step.id
            out.append(FlatStep(id=full_id, step=step, parent_id=parent_id))
    return out


def _flatten_one(step: Step, parent_id: str) -> list[FlatStep]:
    if step.is_composite:
        prefix = f"{parent_id}.{step.id}"
        out: list[FlatStep] = []
        for child in step.children:
            out.extend(_flatten_one(child, prefix))
        return out
    return [FlatStep(id=f"{parent_id}.{step.id}", step=step, parent_id=parent_id)]


def artifact_graph_mermaid(steps: Sequence[Step]) -> str:
    """Generate mermaid flowchart from declared reads/writes (documentation + test helper)."""
    lines = ["flowchart LR"]
    producers: dict[ArtifactKey, str] = {}
    for flat in flatten_steps(steps):
        for w in flat.step.writes:
            producers[w] = flat.id
    for flat in flatten_steps(steps):
        for r in flat.step.reads:
            src = producers.get(r, r.value)
            lines.append(f'  {src} -->|{r.value}| {flat.id}')
    return "\n".join(lines)
```

### d. Written explanation connecting changes to broader picture

Flow primitives separate **what the runbook declares** (structure + data dependencies) from **how the engine executes** (always linear over flattened leaves). That lets `post_tick.py` read as a dataflow spec—parallel fetch blocks and rank→brief chains—while avoiding premature async complexity. `reads_optional` documents steps like `fetch_search_references` that may skip without failing the run. The engine (task 6) only needs `flatten_steps` + leaf `step.run`; composites never appear in outcome logs as opaque `timeline.run`.

---

## Section 3 – Decision Defense

### Chosen path: declarative Step graph + flatten for execution

| Alternative | Why not chosen |
|-------------|----------------|
| **Keep flat tuples; document I/O in comments** | Comments drift; no machine-checkable graph or mermaid generation. |
| **DAG workflow engine (Airflow-style)** | Overkill for ~10 steps; violates “readable runbook” design goal. |
| **True parallel execution now** | Adds failure/retry complexity; sequential composite runner matches today’s behavior. |
| **Merge rank+brief into one step** | Violates locked expanded-step decision; hides LLM vs deterministic boundary. |

### `parallel` and `chain` share sequential runner (v1)

Both composites run children in order. Semantics differ for **documentation and I/O aggregation** only. `chain` preserves rank→brief ordering; `parallel` groups independent branches (timeline vs search fetch; external vs own-post analysis). True concurrent fetch remains an explicit follow-up.

### Dotted step IDs

Nested IDs (`fetch_external_references.fetch_timeline_references`) make `PipelineOutcomeRepository` traces grep-friendly and distinguish leaf steps from legacy names like `profile`. Force-post SSE IDs stay separate (out of scope).

### Frontend

**N/A** — backend runbook structure only.

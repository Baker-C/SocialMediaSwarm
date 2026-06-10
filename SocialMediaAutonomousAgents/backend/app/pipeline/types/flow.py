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
    """One runbook step with declared artifact I/O."""

    id: str
    run: StepFn
    reads: tuple[ArtifactKey, ...] = ()
    writes: tuple[ArtifactKey, ...] = ()
    reads_optional: frozenset[ArtifactKey] = field(default_factory=frozenset)
    purpose: str = ""
    children: tuple[Step, ...] = ()
    composite_kind: CompositeKind = "leaf"

    @property
    def is_composite(self) -> bool:
        return self.composite_kind != "leaf"


def _run_children(children: tuple[Step, ...]) -> StepFn:
    def _run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
        last: StepResult = StepResult(ok=True)
        for child in children:
            last = child.run(ctx, deps)
            if not last.ok and not last.skipped:
                return last
        return last

    return _run


def parallel(*steps: Step, id: str, purpose: str = "") -> Step:
    """Run child steps sequentially; logs use parent.child ids via flatten_steps."""
    reads: set[ArtifactKey] = set()
    writes: set[ArtifactKey] = set()
    optional: set[ArtifactKey] = set()
    for s in steps:
        reads.update(s.reads)
        writes.update(s.writes)
        optional.update(s.reads_optional)
    return Step(
        id=id,
        run=_run_children(steps),
        reads=tuple(reads),
        writes=tuple(writes),
        reads_optional=frozenset(optional),
        purpose=purpose or f"Parallel block: {', '.join(s.id for s in steps)}",
        children=steps,
        composite_kind="parallel",
    )


def chain(*steps: Step, id: str, purpose: str = "") -> Step:
    """Run child steps in order (rank then brief within a branch)."""
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
        run=_run_children(steps),
        reads=tuple(reads),
        writes=tuple(writes),
        reads_optional=frozenset(optional),
        purpose=purpose or " → ".join(s.id for s in steps),
        children=steps,
        composite_kind="chain",
    )


@dataclass(frozen=True)
class FlatStep:
    """Leaf step with full dotted id for logging."""

    id: str
    step: Step
    parent_id: str | None = None


def flatten_steps(steps: Sequence[Step], *, parent_id: str | None = None) -> list[FlatStep]:
    """Expand parallel/chain composites into executable leaf steps with dotted ids."""
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
    """Generate a mermaid flowchart from declared reads/writes (documentation helper)."""
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

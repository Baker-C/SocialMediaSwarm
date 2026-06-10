"""Runbook flow primitives: Step, parallel, chain, flatten_steps."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.flow import Step, chain, flatten_steps, parallel
from app.pipeline.types.tool import StepResult


def _ok_step(step_id: str) -> Step:
    def _run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
        _ = ctx, deps
        return StepResult(ok=True)

    return Step(id=step_id, run=_run)


def test_flatten_steps_linear() -> None:
    steps = (_ok_step("a"), _ok_step("b"))
    flat = flatten_steps(steps)
    assert [f.id for f in flat] == ["a", "b"]


def test_flatten_steps_parallel() -> None:
    block = parallel(_ok_step("left"), _ok_step("right"), id="fetch")
    flat = flatten_steps((block,))
    assert [f.id for f in flat] == ["fetch.left", "fetch.right"]


def test_flatten_steps_chain_in_parallel() -> None:
    branch = chain(_ok_step("rank"), _ok_step("brief"), id="analyze")
    block = parallel(branch, _ok_step("other"), id="summarize")
    flat = flatten_steps((block,))
    assert [f.id for f in flat] == [
        "summarize.analyze.rank",
        "summarize.analyze.brief",
        "summarize.other",
    ]


def test_parallel_declares_merged_reads_writes() -> None:
    left = Step(
        "timeline",
        lambda _c, _d: StepResult(ok=True),
        reads=(ArtifactKey.ACCOUNT_BUNDLE,),
        writes=(ArtifactKey.TIMELINE_REFERENCES,),
    )
    right = Step(
        "search",
        lambda _c, _d: StepResult(ok=True),
        reads=(ArtifactKey.ACCOUNT_BUNDLE,),
        writes=(ArtifactKey.SEARCH_REFERENCES,),
    )
    block = parallel(left, right, id="fetch")
    assert ArtifactKey.ACCOUNT_BUNDLE in block.reads
    assert ArtifactKey.TIMELINE_REFERENCES in block.writes
    assert ArtifactKey.SEARCH_REFERENCES in block.writes


def test_chain_preserves_step_order() -> None:
    calls: list[str] = []

    def make(step_id: str) -> Step:
        def _run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
            _ = ctx, deps
            calls.append(step_id)
            return StepResult(ok=True)

        return Step(id=step_id, run=_run)

    block = chain(make("rank"), make("brief"), id="analyze")
    deps = PostRunDeps(tick_data=MagicMock(), repo=MagicMock())
    block.run(TickRunContext(account_id="a", slot="s"), deps)
    assert calls == ["rank", "brief"]

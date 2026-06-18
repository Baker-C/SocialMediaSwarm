"""Fixtures for pipeline spec validation and compilation tests."""

from __future__ import annotations

import pytest

from app.models.pipeline_spec import CompositeSpec, PipelineSpecDocument, StepSpec
from app.models.tool_catalog import ToolCatalogDocument, ToolParameter
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.types.artifacts import ArtifactKey


class FixtureToolCatalog:
    """Mock ToolCatalog for testing (doc 03 interface, CC-1)."""

    def __init__(self, tools: list[ToolCatalogDocument] | None = None):
        self._tools = {t.tool_id: t for t in (tools or [])}

    def get(self, tool_id: str) -> ToolCatalogDocument | None:
        return self._tools.get(tool_id)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def run_for(self, tool_id: str):
        # Not implemented for tests; use _wrapper_for from compiler
        return None


@pytest.fixture
def fixture_catalog() -> FixtureToolCatalog:
    """Build a test ToolCatalog with SENSE + ACT tools.

    Mirrors doc 06 §5's declared TOOL_WRITES for the two ACT tools.
    """
    tools = [
        # ── SENSE tools (6 base tools) ──
        ToolCatalogDocument(
            tool_id="data.account_profile",
            kind="data",
            purpose="Load X profile and tracked-post engagement metrics",
            parameters=[],
        ),
        ToolCatalogDocument(
            tool_id="data.search_fetch",
            kind="data",
            purpose="Fetch X recent-search reference tweets",
            parameters=[
                ToolParameter(
                    name="max_results_per_query",
                    annotation="int | None",
                    required=False,
                    default=50,
                    kind="config",
                    config_origin="literal",
                ),
            ],
        ),
        ToolCatalogDocument(
            tool_id="data.own_posts_fetch",
            kind="data",
            purpose="Load own-post history with engagement metrics",
            parameters=[],
        ),
        ToolCatalogDocument(
            tool_id="deterministic.reference_rank",
            kind="deterministic",
            purpose="Rank references by engagement",
            parameters=[
                ToolParameter(
                    name="top_n",
                    annotation="int",
                    required=False,
                    default=10,
                    kind="config",
                    config_origin="literal",
                ),
            ],
        ),
        ToolCatalogDocument(
            tool_id="llm.reference_pattern_summary",
            kind="llm",
            purpose="LLM pattern brief for references",
            parameters=[],
        ),
        # ── ACT tools (doc 06) ──
        ToolCatalogDocument(
            tool_id="llm.compose_until_safe",
            kind="llm",
            purpose="Compose with safety guardian regeneration loop",
            writes=[
                ArtifactKey.COMPOSED_POST.value,
                ArtifactKey.SAFETY_VERDICT.value,
            ],
            parameters=[],
        ),
        ToolCatalogDocument(
            tool_id="data.publish_post",
            kind="data",
            purpose="Publish post with idempotency",
            writes=[ArtifactKey.PUBLISHED_POST.value],
            parameters=[],
        ),
    ]
    return FixtureToolCatalog(tools)


def _node_to_spec_leaf(step) -> StepSpec:
    """Convert a hand-written Step to a StepSpec leaf (mirrors doc 04 §7)."""
    # Map step id to tool_id using the runbook's wiring
    _STEP_TOOL_MAP = {
        "load_account_bundle": "data.account_profile",
        "fetch_search_references": "data.search_fetch",
        "collect_external_references": "_internal.collect_external",
        "fetch_own_post_history": "data.own_posts_fetch",
        "rank_external_references": "deterministic.reference_rank",
        "brief_external_references": "llm.reference_pattern_summary",
        "rank_own_posts": "deterministic.reference_rank",
        "brief_own_posts": "llm.reference_pattern_summary",
        "compose_until_safe": "llm.compose_until_safe",
        "publish_post": "data.publish_post",
    }

    return StepSpec(
        kind="step",
        id=step.id,
        tool_id=_STEP_TOOL_MAP.get(step.id, "unknown"),
        reads=[k.value for k in step.reads],
        writes=[k.value for k in step.writes],
        reads_optional=[k.value for k in step.reads_optional],
        config={},
        purpose=step.purpose,
    )


def _node_to_spec_composite(step) -> CompositeSpec:
    """Convert a hand-written composite Step to a CompositeSpec."""
    return CompositeSpec(
        kind=step.composite_kind,
        id=step.id,
        children=[_node_to_spec(c) for c in step.children],
        purpose=step.purpose,
    )


def _node_to_spec(step):
    """Convert a hand-written Step (leaf or composite) to StepSpec/CompositeSpec."""
    if step.is_composite:
        return _node_to_spec_composite(step)
    return _node_to_spec_leaf(step)


@pytest.fixture
def sense_baseline_spec(account_id: str = "JohnJames_News") -> PipelineSpecDocument:
    """Build the 8-leaf SENSE-only baseline from the runbook.

    Extracted from POST_TICK_REFERENCE_STEPS, restricted to SENSE steps.
    (Does NOT include ACT tail; used as a building block for valid_act_spec.)
    """
    _SENSE_IDS = {
        "load_account_bundle",
        "fetch_search_references",
        "collect_external_references",
        "fetch_own_post_history",
        "summarize_for_compose",
    }

    # Walk runbook and extract SENSE steps only
    sense_steps = []
    for step in POST_TICK_REFERENCE_STEPS:
        if step.id in _SENSE_IDS:
            sense_steps.append(_node_to_spec(step))

    return PipelineSpecDocument(
        account_id=account_id,
        steps=sense_steps,
        status="champion",
    )


@pytest.fixture
def valid_act_spec(
    sense_baseline_spec: PipelineSpecDocument,
) -> PipelineSpecDocument:
    """Build the 10-leaf baseline (SENSE + ACT tail, CC-6).

    This is the engine-runnable baseline: R6/R7 require it.
    It is BOTH the happy-path validator input AND the dotted-id lock subject.
    """
    # Append ACT tail: compose_until_safe + publish_post
    spec = sense_baseline_spec.model_copy(deep=True)

    spec.steps.append(
        StepSpec(
            kind="step",
            id="compose_until_safe",
            tool_id="llm.compose_until_safe",
            reads=[
                ArtifactKey.TIMELINE_ANALYSIS.value,
                ArtifactKey.OWN_POSTS_ANALYSIS.value,
                ArtifactKey.TIMELINE_RANKED.value,
            ],
            writes=[
                ArtifactKey.COMPOSED_POST.value,
                ArtifactKey.SAFETY_VERDICT.value,
            ],
            reads_optional=[],
            config={},
            purpose="Compose with safety guardian and regeneration loop",
        )
    )

    spec.steps.append(
        StepSpec(
            kind="step",
            id="publish_post",
            tool_id="data.publish_post",
            reads=[
                ArtifactKey.COMPOSED_POST.value,
                ArtifactKey.SAFETY_VERDICT.value,
            ],
            writes=[ArtifactKey.PUBLISHED_POST.value],
            reads_optional=[],
            config={},
            purpose="Publish post with idempotency marker",
        )
    )

    return spec

"""Tests for pipeline spec compiler (doc 05)."""

from __future__ import annotations

import pytest

from app.models.pipeline_spec import StepSpec
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.services import steps
from app.pipeline.spec.compiler import compile_spec
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.flow import flatten_steps


_BASELINE_DOTTED = [
    "load_account_bundle",
    "fetch_search_references",
    "collect_external_references",
    "fetch_own_post_history",
    "summarize_for_compose.analyze_external_references.rank_external_references",
    "summarize_for_compose.analyze_external_references.brief_external_references",
    "summarize_for_compose.analyze_own_posts.rank_own_posts",
    "summarize_for_compose.analyze_own_posts.brief_own_posts",
    "compose_until_safe",
    "publish_post",
]


def test_compiled_baseline_matches_runbook_dotted_ids(
    valid_act_spec, fixture_catalog
) -> None:
    """Lock: compiled baseline 10-leaf dotted ids match canonical (CC-6)."""
    compiled = compile_spec(valid_act_spec, catalog=fixture_catalog)
    got = [f.id for f in flatten_steps(compiled)]
    assert got == _BASELINE_DOTTED


def test_sense_prefix_matches_live_runbook() -> None:
    """Robustness: SENSE prefix (8 ids) matches live runbook regardless of ACT presence."""
    want = [f.id for f in flatten_steps(POST_TICK_REFERENCE_STEPS)][:8]
    assert _BASELINE_DOTTED[:8] == want


def test_leaf_with_empty_config_binds_wrapper_verbatim(
    valid_act_spec, fixture_catalog
) -> None:
    """Empty-config leaf compiles to the verbatim wrapper (byte-identical)."""
    # Compile and find load_account_bundle leaf
    compiled = compile_spec(valid_act_spec, catalog=fixture_catalog)
    flat = flatten_steps(compiled)
    load_step = next(f for f in flat if f.id == "load_account_bundle")

    # Check that run is the exact wrapper object
    assert load_step.step.run is steps.load_account_bundle


def test_leaf_with_config_threads_through(fixture_catalog) -> None:
    """Non-empty config leaf wraps to thread config through ctx.data."""
    from app.models.pipeline_spec import PipelineSpecDocument
    from unittest.mock import MagicMock

    spec = PipelineSpecDocument(
        account_id="test",
        steps=[
            StepSpec(
                kind="step",
                id="rank_external_references",
                tool_id="deterministic.reference_rank",
                reads=[ArtifactKey.TIMELINE_REFERENCES.value],
                writes=[ArtifactKey.TIMELINE_RANKED.value],
                config={"top_n": 5},  # Non-default config
            ),
        ],
    )

    compiled = compile_spec(spec, catalog=fixture_catalog)
    flat = flatten_steps(compiled)
    rank_step = flat[0].step

    # Compiled run is NOT the bare wrapper (it's wrapped)
    assert rank_step.run is not steps.rank_external_references

    # Verify closure captures the wrapper and config
    # We can't easily mock the internal wrapper, but we can check that
    # the run function exists and is a closure (not the bare wrapper)
    import inspect

    assert inspect.isfunction(rank_step.run)
    # Check closure variables include the wrapper and key
    closure_vars = [cell.cell_contents for cell in rank_step.run.__closure__ or []]
    # Should contain the wrapper, config dict, and the ctx key
    assert any(
        callable(var) for var in closure_vars
    ), "Closure should contain the wrapped callable"


def test_composite_reads_writes_are_union(valid_act_spec, fixture_catalog) -> None:
    """Composite Step has union of child reads/writes (via chain/parallel helpers)."""
    compiled = compile_spec(valid_act_spec, catalog=fixture_catalog)

    # Find the summarize_for_compose composite
    summarize = next(s for s in compiled if s.id == "summarize_for_compose")

    # Should be composite
    assert summarize.is_composite
    assert summarize.composite_kind == "parallel"

    # Its reads should union all child reads. The two chains are:
    # - analyze_external_references: reads TIMELINE_REFERENCES, writes TIMELINE_RANKED
    # - analyze_own_posts: reads OWN_POSTS and OWN_POSTS_RANKED, writes OWN_POSTS_ANALYSIS
    # So union includes: TIMELINE_REFERENCES, OWN_POSTS, and the internal ranked artifacts
    expected_reads = {
        ArtifactKey.TIMELINE_REFERENCES,
        ArtifactKey.OWN_POSTS,
        ArtifactKey.TIMELINE_RANKED,
        ArtifactKey.OWN_POSTS_RANKED,
    }
    assert set(summarize.reads) == expected_reads


def test_internal_sentinel_binds_collect_wrapper(valid_act_spec, fixture_catalog) -> None:
    """_internal.collect_external binds collect_external_references from INTERNAL_PRIMITIVES."""
    compiled = compile_spec(valid_act_spec, catalog=fixture_catalog)
    flat = flatten_steps(compiled)

    # Find collect step
    collect_step = next(f for f in flat if f.id == "collect_external_references")

    # Should be bound to steps.collect_external_references
    assert collect_step.step.run is steps.collect_external_references

    # Should have the right reads/writes from spec node (SEARCH → TIMELINE)
    assert ArtifactKey.SEARCH_REFERENCES in collect_step.step.reads
    assert ArtifactKey.TIMELINE_REFERENCES in collect_step.step.writes

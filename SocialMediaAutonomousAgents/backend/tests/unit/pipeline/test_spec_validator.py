"""Tests for pipeline spec validator (doc 05)."""

from __future__ import annotations

import pytest

from app.models.pipeline_spec import StepSpec
from app.models.tool_catalog import ToolCatalogDocument, ToolParameter
from app.pipeline.spec.validator import validate_spec
from app.pipeline.types.artifacts import ArtifactKey


def test_happy_path_act_baseline_ok(
    valid_act_spec, fixture_catalog
) -> None:
    """The 10-leaf baseline (SENSE + ACT) passes validation clean."""
    report = validate_spec(valid_act_spec, fixture_catalog)
    assert report.ok is True
    assert report.errors == []


def test_unknown_tool(valid_act_spec, fixture_catalog) -> None:
    """R1: Unknown tool_id is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # Mutate first leaf to unknown tool
    spec.steps[0].tool_id = "data.does_not_exist"

    report = validate_spec(spec, fixture_catalog)
    assert "unknown_tool" in report.codes()
    assert "config_type_mismatch" not in report.codes()  # No config error on unknown


def test_internal_sentinel_is_known(valid_act_spec, fixture_catalog) -> None:
    """R1: _internal.* tool_id is recognized as known."""
    spec = valid_act_spec.model_copy(deep=True)
    # The collect step already uses _internal.collect_external; should pass
    report = validate_spec(spec, fixture_catalog)
    assert "unknown_tool" not in report.codes()


def test_missing_tool_id(valid_act_spec, fixture_catalog) -> None:
    """R1: Missing tool_id is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    spec.steps[0].tool_id = None

    report = validate_spec(spec, fixture_catalog)
    assert "missing_tool_id" in report.codes()


def test_config_type_mismatch(valid_act_spec, fixture_catalog) -> None:
    """R2: Config value type mismatch is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # rank_external_references (index 4.0.0 nested) expects int top_n
    # Mutate to string
    for step in spec.steps:
        if hasattr(step, "children"):  # It's the summarize composite
            for child_composite in step.children:
                if hasattr(child_composite, "children"):
                    for leaf in child_composite.children:
                        if leaf.id == "rank_external_references":
                            leaf.config = {"top_n": "ten"}

    report = validate_spec(spec, fixture_catalog)
    assert "config_type_mismatch" in report.codes()


def test_config_bool_into_int_rejected(valid_act_spec, fixture_catalog) -> None:
    """R2: Bool value into int field is rejected (bool is int subclass in Python)."""
    spec = valid_act_spec.model_copy(deep=True)
    for step in spec.steps:
        if hasattr(step, "children"):
            for child_composite in step.children:
                if hasattr(child_composite, "children"):
                    for leaf in child_composite.children:
                        if leaf.id == "rank_external_references":
                            leaf.config = {"top_n": True}

    report = validate_spec(spec, fixture_catalog)
    assert "config_type_mismatch" in report.codes()


def test_config_unknown_key(valid_act_spec, fixture_catalog) -> None:
    """R2: Config key not in proposable_params is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    for step in spec.steps:
        if hasattr(step, "children"):
            for child_composite in step.children:
                if hasattr(child_composite, "children"):
                    for leaf in child_composite.children:
                        if leaf.id == "rank_external_references":
                            leaf.config = {"frobnicate": 1}

    report = validate_spec(spec, fixture_catalog)
    assert "config_unknown_key" in report.codes()


def test_config_non_proposable_key_rejected(valid_act_spec, fixture_catalog) -> None:
    """R2: Non-proposable config key (wired param) is rejected."""
    spec = valid_act_spec.model_copy(deep=True)
    # store_key is a wired param (compile-time), not proposable
    for step in spec.steps:
        if hasattr(step, "children"):
            for child_composite in step.children:
                if hasattr(child_composite, "children"):
                    for leaf in child_composite.children:
                        if leaf.id == "rank_external_references":
                            leaf.config = {"store_key": "custom_key"}

    report = validate_spec(spec, fixture_catalog)
    assert "config_unknown_key" in report.codes()


def test_config_missing_required(fixture_catalog) -> None:
    """R2: Missing required proposable field is flagged."""
    # Craft a synthetic tool with required literal param
    from tests.unit.pipeline.conftest import FixtureToolCatalog
    from app.models.pipeline_spec import PipelineSpecDocument

    tools = [
        ToolCatalogDocument(
            tool_id="test.required_config",
            kind="deterministic",
            purpose="Test required config",
            parameters=[
                ToolParameter(
                    name="required_field",
                    annotation="str",
                    required=True,
                    default=None,
                    kind="config",
                    config_origin="literal",
                ),
            ],
            writes=["safety_verdict"],
        ),
        ToolCatalogDocument(
            tool_id="data.publish_post",
            kind="data",
            purpose="Publish post",
            parameters=[],
            writes=["published_post"],
        ),
    ]
    catalog = FixtureToolCatalog(tools)

    # Build a valid spec foundation then mutate the test step
    spec = PipelineSpecDocument(
        account_id="test",
        steps=[
            StepSpec(
                kind="step",
                id="test_step",
                tool_id="test.required_config",
                writes=["composed_post", "safety_verdict"],
                config={"other_key": "value"},  # has config but missing required_field
            ),
            StepSpec(
                kind="step",
                id="publish_post",
                tool_id="data.publish_post",
                reads=["composed_post", "safety_verdict"],
                writes=["published_post"],
            ),
        ],
        status="champion",
    )

    report = validate_spec(spec, catalog)
    # Should have both unknown_key error and missing_required error
    assert "config_missing_required" in report.codes()
    assert "config_unknown_key" in report.codes()


def test_dangling_read(valid_act_spec, fixture_catalog) -> None:
    """R3: Leaf reading artifact with no upstream writer is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # Brief external refs reads TIMELINE_RANKED; move it before the ranker
    # Find the brief step and move it to position 1
    for step in spec.steps:
        if hasattr(step, "children"):
            for i, child in enumerate(step.children):
                if hasattr(child, "children"):
                    for leaf in child.children:
                        if leaf.id == "brief_external_references":
                            # Insert a read of something produced after
                            leaf.reads = [ArtifactKey.OWN_POSTS_ANALYSIS.value]

    report = validate_spec(spec, fixture_catalog)
    assert "dangling_read" in report.codes()


def test_forward_reference_cycle(fixture_catalog) -> None:
    """R4: Leaf reading artifact it only writes itself is a cycle."""
    from app.models.pipeline_spec import PipelineSpecDocument

    spec = PipelineSpecDocument(
        account_id="test",
        steps=[
            StepSpec(
                kind="step",
                id="self_read",
                tool_id="data.account_profile",
                reads=["account_bundle"],  # Reads what it writes
                writes=["account_bundle"],
            ),
        ],
    )

    report = validate_spec(spec, fixture_catalog)
    assert "cycle" in report.codes()


def test_duplicate_step_id(fixture_catalog) -> None:
    """R5: Duplicate dotted step id is flagged."""
    from app.models.pipeline_spec import PipelineSpecDocument

    spec = PipelineSpecDocument(
        account_id="test",
        steps=[
            StepSpec(
                kind="step",
                id="step1",
                tool_id="data.account_profile",
                writes=["account_bundle"],
            ),
            StepSpec(
                kind="step",
                id="step1",  # Duplicate
                tool_id="data.search_fetch",
                reads=["account_bundle"],
                writes=["search_references"],
            ),
        ],
    )

    report = validate_spec(spec, fixture_catalog)
    assert "duplicate_step_id" in report.codes()


def test_no_terminal_published(valid_act_spec, fixture_catalog) -> None:
    """R6: No step writes PUBLISHED_POST is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # Remove the publish_post step
    spec.steps = spec.steps[:-1]

    report = validate_spec(spec, fixture_catalog)
    assert "no_terminal_published" in report.codes()


def test_step_after_publish(valid_act_spec, fixture_catalog) -> None:
    """R6: Step executing after publish is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # Add a leaf after publish_post
    spec.steps.append(
        StepSpec(
            kind="step",
            id="extra_step",
            tool_id="data.account_profile",
            writes=["account_bundle"],
        )
    )

    report = validate_spec(spec, fixture_catalog)
    assert "step_after_publish" in report.codes()


def test_missing_safety_invariant(valid_act_spec, fixture_catalog) -> None:
    """R7: Missing safety guardian (compose_until_safe) is flagged."""
    spec = valid_act_spec.model_copy(deep=True)
    # Remove compose_until_safe (second-to-last step)
    spec.steps = spec.steps[:-2] + spec.steps[-1:]

    report = validate_spec(spec, fixture_catalog)
    assert "missing_safety_invariant" in report.codes()


def test_missing_publish_invariant(valid_act_spec, fixture_catalog) -> None:
    """R7: Terminal PUBLISHED_POST writer must be from catalog with static writes."""
    spec = valid_act_spec.model_copy(deep=True)
    # Mutate terminal publish to a different tool that declares the write
    # (impossible in closed catalog, but test the logic)
    spec.steps[-1].tool_id = "data.account_profile"  # Wrong tool, no PUBLISHED_POST write

    report = validate_spec(spec, fixture_catalog)
    assert "missing_publish_invariant" in report.codes()

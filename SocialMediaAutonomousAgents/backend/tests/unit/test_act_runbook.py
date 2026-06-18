"""Tests for ACT phase steps appended to POST_TICK_REFERENCE_STEPS runbook."""

from __future__ import annotations

import pytest

from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.flow import flatten_steps


def test_post_tick_steps_includes_compose_and_publish():
    """POST_TICK_REFERENCE_STEPS includes the two ACT steps."""
    step_ids = {step.id for step in POST_TICK_REFERENCE_STEPS}
    assert "compose_until_safe" in step_ids
    assert "publish_post" in step_ids


def test_post_tick_flattened_leaf_count():
    """POST_TICK_REFERENCE_STEPS flattens to 10 leaves (8 SENSE + 2 ACT)."""
    leaves = flatten_steps(POST_TICK_REFERENCE_STEPS)
    leaf_ids = [leaf.id for leaf in leaves]
    assert len(leaves) == 10
    # SENSE leaves (8) - note composite steps get dotted IDs
    assert "load_account_bundle" in leaf_ids
    assert "fetch_search_references" in leaf_ids
    assert "collect_external_references" in leaf_ids
    assert "fetch_own_post_history" in leaf_ids
    assert any("rank_external_references" in lid for lid in leaf_ids)
    assert any("brief_external_references" in lid for lid in leaf_ids)
    assert any("rank_own_posts" in lid for lid in leaf_ids)
    assert any("brief_own_posts" in lid for lid in leaf_ids)
    # ACT leaves (2)
    assert "compose_until_safe" in leaf_ids
    assert "publish_post" in leaf_ids


def test_compose_until_safe_step():
    """compose_until_safe Step has correct reads/writes (from top-level tuple)."""
    compose = None
    for step in POST_TICK_REFERENCE_STEPS:
        if step.id == "compose_until_safe":
            compose = step
            break
    assert compose is not None
    assert compose.reads == (
        ArtifactKey.TIMELINE_ANALYSIS,
        ArtifactKey.OWN_POSTS_ANALYSIS,
        ArtifactKey.TIMELINE_RANKED,
    )
    assert compose.writes == (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)


def test_publish_post_step():
    """publish_post Step has correct reads/writes (from top-level tuple)."""
    publish = None
    for step in POST_TICK_REFERENCE_STEPS:
        if step.id == "publish_post":
            publish = step
            break
    assert publish is not None
    assert publish.reads == (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)
    assert publish.writes == (ArtifactKey.PUBLISHED_POST,)


def test_act_steps_are_top_level():
    """compose_until_safe and publish_post are top-level (not nested in composites)."""
    top_level_ids = {step.id for step in POST_TICK_REFERENCE_STEPS if not step.is_composite}
    assert "compose_until_safe" in top_level_ids
    assert "publish_post" in top_level_ids


def test_compose_step_callable():
    """compose_step wrapper is callable from steps module."""
    from app.pipeline.services.steps import compose_step
    assert callable(compose_step)


def test_publish_step_callable():
    """publish_step wrapper is callable from steps module."""
    from app.pipeline.services.steps import publish_step
    assert callable(publish_step)


def test_runbook_tuple_structure():
    """POST_TICK_REFERENCE_STEPS is a tuple with 7 total entries (5 non-composite + 1 composite + 2 ACT)."""
    assert isinstance(POST_TICK_REFERENCE_STEPS, tuple)
    # 4 non-composite + 1 composite (summarize_for_compose) + 2 ACT steps = 7 total
    assert len(POST_TICK_REFERENCE_STEPS) == 7, f"Expected 7 top-level steps, got {len(POST_TICK_REFERENCE_STEPS)}"
    # Verify the structure includes both ACT steps
    act_steps = {s.id for s in POST_TICK_REFERENCE_STEPS if s.id in ("compose_until_safe", "publish_post")}
    assert act_steps == {"compose_until_safe", "publish_post"}

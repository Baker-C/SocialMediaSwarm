"""Tests for pipeline spec seed builder."""

import pytest

from app.models.pipeline_spec import CompositeSpec, PipelineSpecDocument, StepSpec
from scripts.seed_pipeline_spec import spec_from_runbook


class TestSpecFromRunbook:
    """Test seed builder that converts runbook to spec."""

    def test_spec_from_runbook_creates_document(self):
        """Seed builder creates a valid PipelineSpecDocument."""
        spec = spec_from_runbook("JohnJames_News")

        assert isinstance(spec, PipelineSpecDocument)
        assert spec.account_id == "JohnJames_News"
        assert spec.status == "champion"

    def test_spec_from_runbook_has_steps(self):
        """Spec has steps from the runbook."""
        spec = spec_from_runbook("JohnJames_News")

        assert len(spec.steps) > 0
        # Top-level should have 4 SENSE leaves + 1 parallel composite + 2 ACT leaves
        assert len(spec.steps) >= 6

    def test_spec_has_act_tail_leaves(self):
        """Spec includes the two ACT-tail leaves."""
        spec = spec_from_runbook("JohnJames_News")

        # Flatten all step IDs to check for ACT leaves
        all_ids = _collect_step_ids(spec.steps)

        assert "compose_until_safe" in all_ids
        assert "publish_post" in all_ids

    def test_spec_has_sense_leaves(self):
        """Spec includes all 8 SENSE leaves."""
        spec = spec_from_runbook("JohnJames_News")

        all_ids = _collect_step_ids(spec.steps)

        sense_ids = {
            "load_account_bundle",
            "fetch_search_references",
            "collect_external_references",
            "fetch_own_post_history",
            "rank_external_references",
            "brief_external_references",
            "rank_own_posts",
            "brief_own_posts",
        }
        assert sense_ids.issubset(all_ids)

    def test_spec_has_correct_total_leaf_count(self):
        """Spec has exactly 10 leaf steps (8 SENSE + 2 ACT)."""
        spec = spec_from_runbook("JohnJames_News")

        leaf_count = _count_leaf_steps(spec.steps)
        assert leaf_count == 10

    def test_spec_preserves_runbook_structure(self):
        """Spec preserves the nested structure of the runbook."""
        spec = spec_from_runbook("JohnJames_News")

        # Runbook has a parallel composite at the top level
        assert any(
            isinstance(s, CompositeSpec) and s.kind == "parallel" for s in spec.steps
        )

    def test_leaf_steps_have_tool_ids(self):
        """All leaf steps have valid tool_ids from STEP_TOOL_MAP."""
        spec = spec_from_runbook("JohnJames_News")

        for leaf in _collect_leaf_steps(spec.steps):
            assert leaf.tool_id is not None
            assert len(leaf.tool_id) > 0

    def test_leaf_steps_have_artifacts(self):
        """Leaf steps have artifact reads/writes populated."""
        spec = spec_from_runbook("JohnJames_News")

        # At least some leaves should have reads or writes
        leaves = _collect_leaf_steps(spec.steps)
        has_artifacts = any(len(leaf.reads) > 0 or len(leaf.writes) > 0 for leaf in leaves)
        assert has_artifacts

    def test_act_tail_leaves_have_correct_reads_writes(self):
        """ACT tail leaves have correct artifact definitions."""
        spec = spec_from_runbook("JohnJames_News")

        leaves = {leaf.id: leaf for leaf in _collect_leaf_steps(spec.steps)}

        compose = leaves["compose_until_safe"]
        assert "timeline_analysis" in compose.reads
        assert "own_posts_analysis" in compose.reads
        assert "timeline_ranked" in compose.reads
        assert "composed_post" in compose.writes
        assert "safety_verdict" in compose.writes

        publish = leaves["publish_post"]
        assert "composed_post" in publish.reads
        assert "safety_verdict" in publish.reads
        assert "published_post" in publish.writes

    def test_proposable_config_populated(self):
        """Some steps have proposable config populated."""
        spec = spec_from_runbook("JohnJames_News")

        leaves = {leaf.id: leaf for leaf in _collect_leaf_steps(spec.steps)}

        # rank_external_references and rank_own_posts should have top_n config
        if "rank_external_references" in leaves:
            rank_ext = leaves["rank_external_references"]
            assert rank_ext.config.get("top_n") == 10

        if "rank_own_posts" in leaves:
            rank_own = leaves["rank_own_posts"]
            assert rank_own.config.get("top_n") == 10

        # fetch_search_references should have max_results_per_query
        if "fetch_search_references" in leaves:
            fetch = leaves["fetch_search_references"]
            assert fetch.config.get("max_results_per_query") == 50

    def test_version_not_stamped_by_builder(self):
        """Builder returns unstamped spec (stamp happens on save)."""
        spec = spec_from_runbook("JohnJames_News")

        # Version stamp is applied by repo.save, not by builder
        assert spec.version_hash is None


def _collect_step_ids(steps: list) -> set[str]:
    """Recursively collect all step IDs from a step tree."""
    ids = set()
    for step in steps:
        ids.add(step.id)
        if isinstance(step, CompositeSpec) and step.children:
            ids.update(_collect_step_ids(step.children))
    return ids


def _count_leaf_steps(steps: list) -> int:
    """Count all leaf (non-composite) steps."""
    count = 0
    for step in steps:
        if isinstance(step, CompositeSpec):
            count += _count_leaf_steps(step.children)
        else:
            count += 1
    return count


def _collect_leaf_steps(steps: list) -> list[StepSpec]:
    """Collect all leaf steps into a flat list."""
    leaves = []
    for step in steps:
        if isinstance(step, CompositeSpec):
            leaves.extend(_collect_leaf_steps(step.children))
        else:
            leaves.append(step)
    return leaves

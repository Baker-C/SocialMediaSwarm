"""Tests for pipeline spec models and versioning."""

import pytest
from app.models.pipeline_spec import CompositeSpec, PipelineSpecDocument, StepSpec
from app.models.pipeline_revision import PipelineRevisionDocument


class TestStepSpec:
    """Test StepSpec leaf node model."""

    def test_step_spec_minimal(self):
        """Create a minimal step with required fields."""
        step = StepSpec(id="test_step", tool_id="data.test")
        assert step.id == "test_step"
        assert step.tool_id == "data.test"
        assert step.kind == "step"
        assert step.reads == []
        assert step.writes == []
        assert step.config == {}

    def test_step_spec_with_artifacts(self):
        """Create a step with artifact reads/writes."""
        step = StepSpec(
            id="rank_posts",
            tool_id="deterministic.reference_rank",
            reads=["timeline_references"],
            writes=["timeline_ranked"],
            reads_optional=["metadata"],
            purpose="Rank references",
        )
        assert step.reads == ["timeline_references"]
        assert step.writes == ["timeline_ranked"]
        assert step.reads_optional == ["metadata"]
        assert step.purpose == "Rank references"

    def test_step_spec_with_config(self):
        """Create a step with proposable config."""
        step = StepSpec(
            id="fetch_refs",
            tool_id="data.search_fetch",
            config={"max_results_per_query": 50},
        )
        assert step.config == {"max_results_per_query": 50}

    def test_step_spec_kind_always_step(self):
        """Verify kind is always 'step' for leaf nodes."""
        step = StepSpec(id="x", tool_id="y")
        assert step.kind == "step"


class TestCompositeSpec:
    """Test CompositeSpec composite node model."""

    def test_composite_parallel_empty(self):
        """Create a parallel composite with no children."""
        comp = CompositeSpec(kind="parallel", id="root")
        assert comp.kind == "parallel"
        assert comp.id == "root"
        assert comp.children == []

    def test_composite_chain_empty(self):
        """Create a chain composite."""
        comp = CompositeSpec(kind="chain", id="process")
        assert comp.kind == "chain"
        assert comp.id == "process"

    def test_composite_with_leaf_children(self):
        """Create a composite with leaf children."""
        child1 = StepSpec(id="step1", tool_id="tool1")
        child2 = StepSpec(id="step2", tool_id="tool2")
        comp = CompositeSpec(kind="chain", id="process", children=[child1, child2])
        assert len(comp.children) == 2
        assert comp.children[0].id == "step1"
        assert comp.children[1].id == "step2"

    def test_composite_nested(self):
        """Create a nested composite (composite containing composites and leaves)."""
        leaf1 = StepSpec(id="leaf1", tool_id="t1")
        leaf2 = StepSpec(id="leaf2", tool_id="t2")
        inner_chain = CompositeSpec(kind="chain", id="inner", children=[leaf1, leaf2])

        leaf3 = StepSpec(id="leaf3", tool_id="t3")
        outer_parallel = CompositeSpec(kind="parallel", id="outer", children=[inner_chain, leaf3])

        assert outer_parallel.kind == "parallel"
        assert len(outer_parallel.children) == 2
        assert isinstance(outer_parallel.children[0], CompositeSpec)
        assert isinstance(outer_parallel.children[1], StepSpec)

    def test_composite_purpose(self):
        """Composite can have a purpose."""
        comp = CompositeSpec(
            kind="parallel", id="analyze", purpose="Run both analysis branches in parallel"
        )
        assert comp.purpose == "Run both analysis branches in parallel"


class TestPipelineSpecDocument:
    """Test the main pipeline spec document."""

    def test_spec_minimal(self):
        """Create minimal spec."""
        spec = PipelineSpecDocument(account_id="test_account")
        assert spec.account_id == "test_account"
        assert spec.steps == []
        assert spec.status == "champion"
        assert spec.version_seq == 1
        assert spec.version_label == "v1"

    def test_spec_with_steps(self):
        """Create spec with steps."""
        step1 = StepSpec(id="load", tool_id="data.profile")
        step2 = StepSpec(id="fetch", tool_id="data.search")
        spec = PipelineSpecDocument(account_id="acct1", steps=[step1, step2])
        assert len(spec.steps) == 2
        assert spec.steps[0].id == "load"
        assert spec.steps[1].id == "fetch"

    def test_spec_with_nested_steps(self):
        """Create spec with nested composite steps."""
        leaf1 = StepSpec(id="rank", tool_id="deterministic.reference_rank")
        leaf2 = StepSpec(id="brief", tool_id="llm.reference_pattern_summary")
        chain = CompositeSpec(kind="chain", id="analyze", children=[leaf1, leaf2])
        spec = PipelineSpecDocument(account_id="acct1", steps=[chain])
        assert len(spec.steps) == 1
        assert isinstance(spec.steps[0], CompositeSpec)
        assert spec.steps[0].id == "analyze"

    def test_spec_champion_status(self):
        """Test champion status."""
        spec = PipelineSpecDocument(account_id="a", status="champion")
        assert spec.status == "champion"
        assert spec.parent_hash is None

    def test_spec_challenger_status(self):
        """Test challenger status with parent lineage."""
        spec = PipelineSpecDocument(
            account_id="a", status="challenger", parent_hash="abc123def456"
        )
        assert spec.status == "challenger"
        assert spec.parent_hash == "abc123def456"

    def test_document_id_champion(self):
        """Test document ID for champion."""
        doc_id = PipelineSpecDocument.document_id("JohnJames_News")
        assert doc_id == "pipelinespecs/JohnJames_News"

    def test_document_id_challenger(self):
        """Test document ID for challenger."""
        doc_id = PipelineSpecDocument.document_id("JohnJames_News", status="challenger")
        assert doc_id == "pipelinespecs/JohnJames_News-challenger"

    def test_document_id_with_kind(self):
        """Test document ID with kind namespace."""
        doc_id = PipelineSpecDocument.document_id("JohnJames_News", kind="reply")
        assert doc_id == "pipelinespecs-reply/JohnJames_News"

    def test_document_id_challenger_with_kind(self):
        """Test document ID for challenger with kind."""
        doc_id = PipelineSpecDocument.document_id("JohnJames_News", "challenger", "reply")
        assert doc_id == "pipelinespecs-reply/JohnJames_News-challenger"

    def test_version_stamp(self):
        """Test version fields."""
        spec = PipelineSpecDocument(
            account_id="a", version_hash="xyz", version_seq=2, version_label="v2"
        )
        assert spec.version_hash == "xyz"
        assert spec.version_seq == 2
        assert spec.version_label == "v2"


class TestPipelineRevisionDocument:
    """Test immutable revision archive."""

    def test_revision_minimal(self):
        """Create minimal revision."""
        rev = PipelineRevisionDocument(
            account_id="a", seq=1, label="v1", version_hash="h1", changed_at="2024-01-01T00:00:00Z"
        )
        assert rev.account_id == "a"
        assert rev.seq == 1
        assert rev.label == "v1"
        assert rev.version_hash == "h1"
        assert rev.steps == []  # Empty list, not default_factory

    def test_revision_with_steps(self):
        """Create revision with snapshot of steps."""
        step = StepSpec(id="test", tool_id="t")
        rev = PipelineRevisionDocument(
            account_id="a",
            seq=1,
            label="v1",
            version_hash="h1",
            changed_at="2024-01-01T00:00:00Z",
            steps=[step],
        )
        assert len(rev.steps) == 1
        assert rev.steps[0].id == "test"

    def test_revision_status_and_lineage(self):
        """Test status and parent lineage fields."""
        rev = PipelineRevisionDocument(
            account_id="a",
            seq=2,
            label="v2",
            version_hash="h2",
            changed_at="2024-01-02T00:00:00Z",
            status="champion",
            parent_hash="h1",
        )
        assert rev.status == "champion"
        assert rev.parent_hash == "h1"

    def test_document_id(self):
        """Test revision document ID."""
        doc_id = PipelineRevisionDocument.document_id("JohnJames_News", 1)
        assert doc_id == "pipelinerevisions/JohnJames_News-v1"

    def test_document_id_various(self):
        """Test revision IDs for various sequences."""
        assert PipelineRevisionDocument.document_id("acct", 1) == "pipelinerevisions/acct-v1"
        assert PipelineRevisionDocument.document_id("acct", 5) == "pipelinerevisions/acct-v5"
        assert (
            PipelineRevisionDocument.document_id("acct_with_underscore", 10)
            == "pipelinerevisions/acct_with_underscore-v10"
        )

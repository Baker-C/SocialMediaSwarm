"""Tests for reply pipeline spec and kind support (doc 12)."""

from __future__ import annotations

import pytest

from app.models.pipeline_spec import (
    PipelineSpecDocument,
    StepSpec,
)
from app.pipeline.spec.catalog import get_tool_catalog
from app.pipeline.spec.compiler import compile_spec
from app.pipeline.spec.validator import validate_spec
from app.pipeline.types.artifacts import ArtifactKey


class TestDocumentIdKind:
    """Test document_id with kind parameter."""

    def test_post_id_byte_identical_to_before(self):
        """Verify post id is unchanged."""
        doc_id = PipelineSpecDocument.document_id("test_account", "champion", kind="post")
        assert doc_id == "pipelinespecs/test_account"

    def test_post_id_without_kind_defaults_to_post(self):
        """Default kind='post' preserves backward compatibility."""
        doc_id = PipelineSpecDocument.document_id("test_account", "champion")
        assert doc_id == "pipelinespecs/test_account"

    def test_reply_id_namespaced_by_prefix(self):
        """Reply id uses prefix namespacing."""
        doc_id = PipelineSpecDocument.document_id("test_account", "champion", kind="reply")
        assert doc_id == "pipelinespecs-reply/test_account"

    def test_challenger_post_id(self):
        """Challenger post id uses suffix."""
        doc_id = PipelineSpecDocument.document_id("test_account", "challenger", kind="post")
        assert doc_id == "pipelinespecs/test_account-challenger"

    def test_challenger_reply_id(self):
        """Challenger reply id uses both prefix and suffix."""
        doc_id = PipelineSpecDocument.document_id(
            "test_account", "challenger", kind="reply"
        )
        assert doc_id == "pipelinespecs-reply/test_account-challenger"


class TestReplyArtifactKeys:
    """Test that reply artifact keys are registered."""

    def test_reply_artifact_keys_exist(self):
        """All 5 reply artifact keys are defined."""
        assert ArtifactKey.MENTIONS
        assert ArtifactKey.MENTIONS_RANKED
        assert ArtifactKey.REPLY_DRAFT
        assert ArtifactKey.REPLY_VERDICT
        assert ArtifactKey.REPLY_RESULT

    def test_artifact_keys_have_values(self):
        """Reply artifacts have string values for ctx lookup."""
        assert ArtifactKey.MENTIONS.value == "mentions"
        assert ArtifactKey.MENTIONS_RANKED.value == "mentions_ranked"
        assert ArtifactKey.REPLY_DRAFT.value == "reply_draft"
        assert ArtifactKey.REPLY_VERDICT.value == "reply_verdict"
        assert ArtifactKey.REPLY_RESULT.value == "reply_result"

    def test_reply_artifact_keys_in_artifact_key_lookup(self):
        """Reply artifacts are in the ARTIFACT_KEY_BY_CTX_KEY mapping."""
        from app.pipeline.types.artifacts import (
            ARTIFACT_KEY_BY_CTX_KEY,
            artifact_key_for_ctx_key,
        )

        assert "mentions" in ARTIFACT_KEY_BY_CTX_KEY
        assert "mentions_ranked" in ARTIFACT_KEY_BY_CTX_KEY
        assert "reply_draft" in ARTIFACT_KEY_BY_CTX_KEY
        assert "reply_verdict" in ARTIFACT_KEY_BY_CTX_KEY
        assert "reply_result" in ARTIFACT_KEY_BY_CTX_KEY

        assert artifact_key_for_ctx_key("mentions") == ArtifactKey.MENTIONS
        assert artifact_key_for_ctx_key("reply_result") == ArtifactKey.REPLY_RESULT


class TestReplyToolCatalog:
    """Test that reply tools are in the catalog."""

    def test_reply_tools_in_catalog(self):
        """All 3 reply tools are registered in the catalog."""
        catalog = get_tool_catalog()
        assert catalog.get("data.mentions_fetch") is not None
        assert catalog.get("llm.reply_compose") is not None
        assert catalog.get("data.reply_publish") is not None

    def test_mentions_fetch_tool_metadata(self):
        """mentions_fetch has correct metadata."""
        catalog = get_tool_catalog()
        tool = catalog.get("data.mentions_fetch")
        assert tool.kind == "data"
        assert "mentions" in tool.writes
        assert "twitter" in [p.name for p in tool.parameters]

    def test_reply_compose_tool_metadata(self):
        """reply_compose has correct metadata."""
        catalog = get_tool_catalog()
        tool = catalog.get("llm.reply_compose")
        assert tool.kind == "llm"
        assert "reply_draft" in tool.writes
        assert "reply_verdict" in tool.writes
        assert "mentions_ranked" in tool.reads

    def test_reply_publish_tool_metadata(self):
        """reply_publish has correct metadata."""
        catalog = get_tool_catalog()
        tool = catalog.get("data.reply_publish")
        assert tool.kind == "data"
        assert "reply_result" in tool.writes
        assert "reply_draft" in tool.reads
        assert "reply_verdict" in tool.reads


class TestValidatorKindParameter:
    """Test that validator accepts and uses kind parameter."""

    def test_validate_spec_with_kind_post(self):
        """Validator accepts kind='post' and validates against post terminals."""
        spec = PipelineSpecDocument(
            account_id="test",
            steps=[
                StepSpec(
                    id="dummy",
                    tool_id="data.account_profile",
                    writes=["account_bundle"],
                ),
            ],
        )
        catalog = get_tool_catalog()
        # This should report missing post terminals (compose, publish)
        report = validate_spec(spec, catalog, kind="post")
        assert not report.ok
        assert any("safety" in str(e.code).lower() for e in report.errors)

    def test_validate_spec_with_kind_reply(self):
        """Validator accepts kind='reply' and validates against reply terminals."""
        spec = PipelineSpecDocument(
            account_id="test",
            steps=[
                StepSpec(
                    id="dummy",
                    tool_id="data.account_profile",
                    writes=["account_bundle"],
                ),
            ],
        )
        catalog = get_tool_catalog()
        # This should report missing reply terminals (reply_compose, reply_publish)
        report = validate_spec(spec, catalog, kind="reply")
        assert not report.ok
        # Should complain about missing reply-specific verdicts/terminals
        error_codes = [e.code for e in report.errors]
        assert any(e in error_codes for e in ["missing_safety_invariant", "no_terminal_published"])

    def test_validate_spec_kind_default_is_post(self):
        """kind defaults to 'post' for backward compat."""
        spec = PipelineSpecDocument(account_id="test", steps=[])
        catalog = get_tool_catalog()
        # Default (post) and explicit kind='post' should behave identically
        report_default = validate_spec(spec, catalog)
        report_explicit = validate_spec(spec, catalog, kind="post")
        assert report_default.ok == report_explicit.ok


class TestReplySpecCompilation:
    """Test that a reply spec can be compiled."""

    def test_compile_minimal_reply_spec(self):
        """A minimal valid reply spec compiles."""
        # This is just a sanity check that the compiler handles reply step ids
        spec = PipelineSpecDocument(
            account_id="test",
            steps=[
                StepSpec(
                    id="fetch_mentions",
                    tool_id="data.mentions_fetch",
                    writes=["mentions"],
                ),
            ],
        )
        catalog = get_tool_catalog()
        graph = compile_spec(spec, catalog=catalog)
        # Should compile without error
        assert len(graph) > 0
        assert graph[0].id == "fetch_mentions"

    def test_compile_reply_compose_step(self):
        """reply_compose step compiles with correct tool binding."""
        spec = PipelineSpecDocument(
            account_id="test",
            steps=[
                StepSpec(
                    id="reply_compose",
                    tool_id="llm.reply_compose",
                    reads=["mentions_ranked"],
                    writes=["reply_draft", "reply_verdict"],
                ),
            ],
        )
        catalog = get_tool_catalog()
        graph = compile_spec(spec, catalog=catalog)
        step = graph[0]
        assert step.id == "reply_compose"
        assert ArtifactKey.REPLY_DRAFT in step.writes
        assert ArtifactKey.REPLY_VERDICT in step.writes

    def test_compile_rank_mentions_step_reuses_reference_rank_tool(self):
        """rank_mentions reuses deterministic.reference_rank tool via wrapper."""
        spec = PipelineSpecDocument(
            account_id="test",
            steps=[
                StepSpec(
                    id="rank_mentions",
                    tool_id="deterministic.reference_rank",
                    reads=["mentions"],
                    writes=["mentions_ranked"],
                    config={"top_n": 10},
                ),
            ],
        )
        catalog = get_tool_catalog()
        graph = compile_spec(spec, catalog=catalog)
        step = graph[0]
        assert step.id == "rank_mentions"
        assert ArtifactKey.MENTIONS_RANKED in step.writes


class TestReplyStepWrappers:
    """Test that reply step wrappers exist and are callable."""

    def test_fetch_mentions_wrapper_exists(self):
        """fetch_mentions wrapper is available."""
        from app.pipeline.services import steps

        assert hasattr(steps, "fetch_mentions")
        assert callable(steps.fetch_mentions)

    def test_rank_mentions_wrapper_exists(self):
        """rank_mentions wrapper is available."""
        from app.pipeline.services import steps

        assert hasattr(steps, "rank_mentions")
        assert callable(steps.rank_mentions)

    def test_reply_compose_step_wrapper_exists(self):
        """reply_compose_step wrapper is available."""
        from app.pipeline.services import steps

        assert hasattr(steps, "reply_compose_step")
        assert callable(steps.reply_compose_step)

    def test_reply_publish_step_wrapper_exists(self):
        """reply_publish_step wrapper is available."""
        from app.pipeline.services import steps

        assert hasattr(steps, "reply_publish_step")
        assert callable(steps.reply_publish_step)


class TestCompilerBindingsForReply:
    """Test that compiler binds reply step ids to correct wrappers."""

    def test_compiler_has_fetch_mentions_binding(self):
        """Compiler maps fetch_mentions step id to wrapper."""
        from app.pipeline.spec.compiler import (
            _wrapper_by_step_id_entry,
        )

        entry = _wrapper_by_step_id_entry("fetch_mentions")
        assert entry is not None
        tool_id, wrapper = entry
        assert tool_id == "data.mentions_fetch"

    def test_compiler_has_rank_mentions_binding(self):
        """Compiler maps rank_mentions step id to wrapper."""
        from app.pipeline.spec.compiler import (
            _wrapper_by_step_id_entry,
        )

        entry = _wrapper_by_step_id_entry("rank_mentions")
        assert entry is not None
        tool_id, wrapper = entry
        assert tool_id == "deterministic.reference_rank"

    def test_compiler_has_reply_compose_binding(self):
        """Compiler maps reply_compose step id to wrapper."""
        from app.pipeline.spec.compiler import (
            _wrapper_by_step_id_entry,
        )

        entry = _wrapper_by_step_id_entry("reply_compose")
        assert entry is not None
        tool_id, wrapper = entry
        assert tool_id == "llm.reply_compose"

    def test_compiler_has_reply_publish_binding(self):
        """Compiler maps reply_publish step id to wrapper."""
        from app.pipeline.spec.compiler import (
            _wrapper_by_step_id_entry,
        )

        entry = _wrapper_by_step_id_entry("reply_publish")
        assert entry is not None
        tool_id, wrapper = entry
        assert tool_id == "data.reply_publish"

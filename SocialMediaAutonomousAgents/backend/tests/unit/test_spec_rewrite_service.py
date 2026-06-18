"""Tests for spec rewrite and self-improvement."""

from unittest.mock import patch

import pytest

from app.models.pipeline_spec import PipelineSpecDocument, StepSpec
from app.models.tool_catalog import ToolCatalogDocument, ToolParameter
from app.pipeline.spec.validator import ValidationReport
from app.services.pipeline_spec_repository import PipelineSpecRepository
from app.services.pipeline_version_service import compute_pipeline_hash
from app.services.spec_rewrite_service import propose_and_stage_challenger


class FakePipelineSpecRepository(PipelineSpecRepository):
    """Stub repository for testing."""

    def __init__(self):
        super().__init__()
        self._docs: dict[str, PipelineSpecDocument] = {}
        self._save_calls: list[PipelineSpecDocument] = []

    def load(self, account_id: str, status: str = "champion", kind: str = "post") -> PipelineSpecDocument | None:
        key = f"{account_id}:{status}:{kind}"
        return self._docs.get(key)

    def save(self, spec: PipelineSpecDocument, kind: str = "post") -> None:
        """Track calls to save for testing."""
        self._save_calls.append(spec)
        key = f"{spec.account_id}:{spec.status}:{kind}"
        self._docs[key] = spec

    def get_save_calls(self) -> list[PipelineSpecDocument]:
        """Return all specs that were saved."""
        return self._save_calls


class FakeToolCatalog:
    """Stub catalog for testing."""

    def __init__(self, tools: list[ToolCatalogDocument] | None = None):
        self._tools = tools or []
        self._by_id = {t.tool_id: t for t in self._tools}

    def get(self, tool_id: str) -> ToolCatalogDocument | None:
        return self._by_id.get(tool_id)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._by_id

    def all(self) -> list[ToolCatalogDocument]:
        return self._tools


class TestProposeAndStageChallenger:
    """Tests for proposal staging and validation."""

    def test_challenger_staged_when_different(self):
        """A valid, distinct proposal is staged with parent_hash and status=challenger."""
        champion = PipelineSpecDocument(
            account_id="test_account",
            steps=[],
            status="champion",
            version_hash="v1_hash",
            version_seq=1,
        )

        repo = FakePipelineSpecRepository()
        repo.save(champion)

        def mock_propose(champ, catalog):
            proposal = PipelineSpecDocument.model_validate(champ.model_dump())
            proposal.steps = [StepSpec(id="modified", tool_id="data.account_profile")]
            return proposal

        hash_counter = [0]

        def mock_compute(spec):
            hash_counter[0] += 1
            return f"hash_{hash_counter[0]}"

        # Patch where the names are USED (spec_rewrite_service imports them by value),
        # NOT where they are defined — patching the validator module is a no-op here.
        with (
            patch("app.services.spec_rewrite_service.validate_spec",
                  return_value=ValidationReport(ok=True, errors=[])),
            patch("app.services.spec_rewrite_service.compute_pipeline_hash", side_effect=mock_compute),
            patch("app.services.spec_rewrite_service._propose_spec", side_effect=mock_propose),
        ):
            result = propose_and_stage_challenger("test_account", repo=repo)

        assert result is not None
        assert result.status == "challenger"
        assert result.parent_hash == "v1_hash"
        assert result.version_hash is None  # force fresh version on save
        assert len(repo.get_save_calls()) == 2  # champion + staged challenger

    def test_challenger_not_staged_when_invalid(self):
        """An invalid proposal is rejected; nothing is staged."""
        champion = PipelineSpecDocument(
            account_id="test_account",
            steps=[],
            status="champion",
            version_hash="v1_hash",
        )

        repo = FakePipelineSpecRepository()
        repo.save(champion)

        import app.pipeline.spec.validator as validator_module

        original_validate = validator_module.validate_spec

        # Mock validate to return NOT OK
        def mock_validate(spec, catalog):
            error = type("Error", (), {"code": "unknown_tool"})()
            report = type("ValidationReport", (), {"ok": False, "errors": [error], "codes": lambda: ["unknown_tool"]})()
            return report

        validator_module.validate_spec = mock_validate

        try:
            import app.services.spec_rewrite_service as rewrite_module

            original_propose = rewrite_module._propose_spec

            def mock_propose(champ, catalog):
                return PipelineSpecDocument.model_validate(champ.model_dump())

            rewrite_module._propose_spec = mock_propose

            try:
                result = propose_and_stage_challenger("test_account", repo=repo)
                assert result is None
                # Only the champion save, no challenger staged
                assert len(repo.get_save_calls()) == 1

            finally:
                rewrite_module._propose_spec = original_propose
        finally:
            validator_module.validate_spec = original_validate

    def test_challenger_not_staged_when_identical(self):
        """A proposal identical to champion is rejected; nothing is staged."""
        champion = PipelineSpecDocument(
            account_id="test_account",
            steps=[StepSpec(id="same", tool_id="data.account_profile")],
            status="champion",
            version_hash="same_hash",
        )

        repo = FakePipelineSpecRepository()
        repo.save(champion)

        def mock_propose(champ, catalog):
            return PipelineSpecDocument.model_validate(champ.model_dump())

        # Both champion and proposal hash to the same value → identity guard returns
        # None before validate_spec is ever reached.
        with (
            patch("app.services.spec_rewrite_service.validate_spec",
                  return_value=ValidationReport(ok=True, errors=[])),
            patch("app.services.spec_rewrite_service.compute_pipeline_hash", return_value="same_hash"),
            patch("app.services.spec_rewrite_service._propose_spec", side_effect=mock_propose),
        ):
            result = propose_and_stage_challenger("test_account", repo=repo)

        assert result is None
        # No challenger staged (identity guard)
        assert len(repo.get_save_calls()) == 1

    def test_challenger_inherits_parent_hash(self):
        """Staged challenger's parent_hash is the champion's version_hash."""
        champion = PipelineSpecDocument(
            account_id="test_account",
            steps=[],
            status="champion",
            version_hash="parent_v1",
        )

        repo = FakePipelineSpecRepository()
        repo.save(champion)

        def mock_propose(champ, catalog):
            p = PipelineSpecDocument.model_validate(champ.model_dump())
            p.steps = [StepSpec(id="different", tool_id="data.account_profile")]
            return p

        counter = [0]

        def mock_compute(spec):
            counter[0] += 1
            return f"hash_{counter[0]}"

        with (
            patch("app.services.spec_rewrite_service.validate_spec",
                  return_value=ValidationReport(ok=True, errors=[])),
            patch("app.services.spec_rewrite_service.compute_pipeline_hash", side_effect=mock_compute),
            patch("app.services.spec_rewrite_service._propose_spec", side_effect=mock_propose),
        ):
            result = propose_and_stage_challenger("test_account", repo=repo)

        assert result is not None
        assert result.parent_hash == "parent_v1"

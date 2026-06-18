"""Tests for pipeline spec and revision repositories."""

import pytest
from unittest.mock import MagicMock, patch

from app.models.pipeline_spec import PipelineSpecDocument, StepSpec
from app.models.pipeline_revision import PipelineRevisionDocument
from app.services.pipeline_revision_repository import PipelineRevisionRepository
from app.services.pipeline_spec_repository import PipelineSpecRepository, promote_challenger


class TestPipelineRevisionRepository:
    """Test revision persistence."""

    def test_save_revision(self):
        """Save a revision to RavenDB."""
        mock_client = MagicMock()
        repo = PipelineRevisionRepository(client=mock_client)

        rev = PipelineRevisionDocument(
            account_id="a",
            seq=1,
            label="v1",
            version_hash="h1",
            changed_at="2024-01-01T00:00:00Z",
        )
        doc_id = repo.save(rev)

        assert doc_id == "pipelinerevisions/a-v1"
        mock_client.put_document.assert_called_once()
        call_args = mock_client.put_document.call_args
        assert call_args[0][0] == "pipelinerevisions/a-v1"
        assert call_args[1]["collection"] == "PipelineRevisions"

    def test_list_for_account(self):
        """List revisions for an account."""
        mock_client = MagicMock()
        mock_client.query.return_value = [
            {
                "@id": "pipelinerevisions/a-v1",
                "account_id": "a",
                "seq": 1,
                "label": "v1",
                "version_hash": "h1",
                "changed_at": "2024-01-01T00:00:00Z",
            },
            {
                "@id": "pipelinerevisions/a-v2",
                "account_id": "a",
                "seq": 2,
                "label": "v2",
                "version_hash": "h2",
                "changed_at": "2024-01-02T00:00:00Z",
            },
        ]
        repo = PipelineRevisionRepository(client=mock_client)

        revs = repo.list_for_account("a")

        assert len(revs) == 2
        assert revs[0].seq == 1
        assert revs[1].seq == 2

    def test_list_for_account_rql_fallback(self):
        """Fall back to ID-based query when collection query fails."""
        mock_client = MagicMock()
        # First query (by collection) fails, second (by id prefix) succeeds
        from app.infrastructure.ravendb_http import RavenDBHttpError

        mock_client.query.side_effect = [
            RavenDBHttpError("Collection not indexed"),
            [
                {
                    "account_id": "a",
                    "seq": 1,
                    "label": "v1",
                    "version_hash": "h1",
                    "changed_at": "2024-01-01T00:00:00Z",
                }
            ],
        ]
        repo = PipelineRevisionRepository(client=mock_client)

        revs = repo.list_for_account("a")

        assert len(revs) == 1
        assert revs[0].seq == 1
        # Verify both queries were attempted
        assert mock_client.query.call_count == 2

    def test_list_for_account_empty_on_double_failure(self):
        """Return empty list when both queries fail."""
        mock_client = MagicMock()
        from app.infrastructure.ravendb_http import RavenDBHttpError

        mock_client.query.side_effect = RavenDBHttpError("Network error")
        repo = PipelineRevisionRepository(client=mock_client)

        revs = repo.list_for_account("a")

        assert revs == []

    def test_list_for_account_strips_metadata(self):
        """Filter out @ metadata keys from rows."""
        mock_client = MagicMock()
        mock_client.query.return_value = [
            {
                "@id": "pipelinerevisions/a-v1",
                "@metadata": {"@collection": "PipelineRevisions"},
                "account_id": "a",
                "seq": 1,
                "label": "v1",
                "version_hash": "h1",
                "changed_at": "2024-01-01T00:00:00Z",
            }
        ]
        repo = PipelineRevisionRepository(client=mock_client)

        revs = repo.list_for_account("a")

        assert len(revs) == 1
        # Metadata keys should not be in the model
        assert not hasattr(revs[0], "@id")

    def test_list_for_account_skips_invalid_rows(self):
        """Skip rows that fail validation."""
        mock_client = MagicMock()
        mock_client.query.return_value = [
            {
                "account_id": "a",
                "seq": 1,
                "label": "v1",
                "version_hash": "h1",
                "changed_at": "2024-01-01T00:00:00Z",
            },
            {
                # Invalid: missing required fields
                "account_id": "a",
            },
            {
                "account_id": "a",
                "seq": 2,
                "label": "v2",
                "version_hash": "h2",
                "changed_at": "2024-01-02T00:00:00Z",
            },
        ]
        repo = PipelineRevisionRepository(client=mock_client)

        revs = repo.list_for_account("a")

        # Should skip the invalid row and return 2 valid ones
        assert len(revs) == 2
        assert revs[0].seq == 1
        assert revs[1].seq == 2


class TestPipelineSpecRepository:
    """Test spec persistence and loading."""

    def test_load_spec(self):
        """Load a spec by document ID."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = {
            "@id": "pipelinespecs/a",
            "account_id": "a",
            "status": "champion",
            "steps": [],
        }
        repo = PipelineSpecRepository(client=mock_client)

        spec = repo.load("a")

        assert spec is not None
        assert spec.account_id == "a"
        assert spec.status == "champion"

    def test_load_spec_not_found(self):
        """Return None when spec doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = None
        repo = PipelineSpecRepository(client=mock_client)

        spec = repo.load("nonexistent")

        assert spec is None

    def test_load_with_status_parameter(self):
        """Load with specific status (champion vs challenger)."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = {
            "account_id": "a",
            "status": "challenger",
            "steps": [],
        }
        repo = PipelineSpecRepository(client=mock_client)

        spec = repo.load("a", status="challenger")

        # Verify correct doc_id was requested
        mock_client.get_document.assert_called_once_with("pipelinespecs/a-challenger")

    def test_load_with_kind_parameter(self):
        """Load with specific kind (post vs reply)."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = {"account_id": "a", "steps": []}
        repo = PipelineSpecRepository(client=mock_client)

        spec = repo.load("a", kind="reply")

        # Verify correct doc_id with kind namespace
        mock_client.get_document.assert_called_once_with("pipelinespecs-reply/a")

    def test_load_or_default_returns_loaded_spec(self):
        """Return loaded spec when it exists."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = {"account_id": "a", "status": "champion", "steps": []}
        repo = PipelineSpecRepository(client=mock_client)

        spec = repo.load_or_default("a")

        assert spec is not None
        assert spec.account_id == "a"

    def test_load_or_default_returns_baseline_when_missing(self):
        """Return seeded baseline when no spec exists."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = None
        repo = PipelineSpecRepository(client=mock_client)

        # Patch where it's imported in the function
        with patch("app.models.pipeline_spec.default_pipeline_spec") as mock_default:
            baseline = PipelineSpecDocument(account_id="a", steps=[])
            mock_default.return_value = baseline

            spec = repo.load_or_default("a")

            assert spec is not None
            assert spec.account_id == "a"
            mock_default.assert_called_once_with("a")

    def test_load_or_default_stamps_baseline_hash(self):
        """In-memory baseline gets stamped with computed hash."""
        mock_client = MagicMock()
        mock_client.get_document.return_value = None
        repo = PipelineSpecRepository(client=mock_client)

        # Patch where it's imported in the function
        with patch("app.models.pipeline_spec.default_pipeline_spec") as mock_default:
            baseline = PipelineSpecDocument(account_id="a", steps=[])
            baseline.version_hash = None  # Ensure it starts unset
            mock_default.return_value = baseline

            spec = repo.load_or_default("a")

            # Baseline should be stamped with a real hash
            assert spec.version_hash is not None
            assert len(spec.version_hash) == 64  # SHA256 hex

    def test_save_bumps_version(self):
        """Save calls version bump."""
        mock_client = MagicMock()
        repo = PipelineSpecRepository(client=mock_client)

        spec = PipelineSpecDocument(account_id="a", steps=[StepSpec(id="s1", tool_id="t1")])

        with patch(
            "app.services.pipeline_spec_repository.bump_pipeline_version_if_needed"
        ) as mock_bump:
            bumped = PipelineSpecDocument(
                account_id="a",
                steps=spec.steps,
                version_hash="h1",
                version_seq=1,
            )
            mock_bump.return_value = bumped

            repo.save(spec)

            mock_bump.assert_called_once()
            # Verify client.put_document was called with the bumped spec
            mock_client.put_document.assert_called_once()
            call_args = mock_client.put_document.call_args
            assert call_args[0][0] == "pipelinespecs/a"

    def test_save_uses_spec_status(self):
        """Save respects the spec's status field."""
        mock_client = MagicMock()
        repo = PipelineSpecRepository(client=mock_client)

        with patch(
            "app.services.pipeline_spec_repository.bump_pipeline_version_if_needed"
        ) as mock_bump:
            spec = PipelineSpecDocument(account_id="a", status="challenger")
            bumped = PipelineSpecDocument(
                account_id="a", status="challenger", version_hash="h1"
            )
            mock_bump.return_value = bumped

            repo.save(spec)

            # Document ID should reflect challenger status
            call_args = mock_client.put_document.call_args
            assert call_args[0][0] == "pipelinespecs/a-challenger"


class TestPromoteChallenger:
    """Test promotion workflow.

    Note: Full end-to-end validation testing requires doc 05's validate_spec and
    compile_spec to be available. These tests verify the basic error cases only.
    """

    def test_promote_nonexistent_challenger_raises(self):
        """Promote raises when no challenger exists."""
        mock_repo = MagicMock()
        mock_repo.load.return_value = None

        with pytest.raises(ValueError, match="no challenger"):
            promote_challenger("a", repo=mock_repo)

"""Tests for pipeline version service."""

import pytest
from unittest.mock import MagicMock

from app.models.pipeline_spec import PipelineSpecDocument, StepSpec
from app.models.pipeline_revision import PipelineRevisionDocument
from app.services.pipeline_version_service import (
    bump_pipeline_version_if_needed,
    compute_pipeline_hash,
)


class TestComputePipelineHash:
    """Test hash computation for pipeline specs."""

    def test_hash_empty_spec(self):
        """Hash of empty spec is stable."""
        spec = PipelineSpecDocument(account_id="a")
        hash1 = compute_pipeline_hash(spec)
        hash2 = compute_pipeline_hash(spec)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex is 64 chars

    def test_hash_single_step(self):
        """Hash with single step."""
        spec = PipelineSpecDocument(
            account_id="a", steps=[StepSpec(id="step1", tool_id="tool1")]
        )
        hash_val = compute_pipeline_hash(spec)
        assert len(hash_val) == 64

    def test_hash_changes_with_step_addition(self):
        """Hash changes when a step is added."""
        spec1 = PipelineSpecDocument(account_id="a")
        hash1 = compute_pipeline_hash(spec1)

        spec2 = PipelineSpecDocument(
            account_id="a", steps=[StepSpec(id="step1", tool_id="tool1")]
        )
        hash2 = compute_pipeline_hash(spec2)

        assert hash1 != hash2

    def test_hash_changes_with_step_reorder(self):
        """Hash changes when steps are reordered (ORDER-SENSITIVE)."""
        step1 = StepSpec(id="a", tool_id="t1")
        step2 = StepSpec(id="b", tool_id="t2")

        spec_ab = PipelineSpecDocument(account_id="acct", steps=[step1, step2])
        spec_ba = PipelineSpecDocument(account_id="acct", steps=[step2, step1])

        hash_ab = compute_pipeline_hash(spec_ab)
        hash_ba = compute_pipeline_hash(spec_ba)
        assert hash_ab != hash_ba

    def test_hash_ignores_status_change(self):
        """Hash is unchanged when status changes (status is not part of hash)."""
        spec1 = PipelineSpecDocument(account_id="a", status="champion")
        hash1 = compute_pipeline_hash(spec1)

        spec2 = PipelineSpecDocument(account_id="a", status="challenger")
        hash2 = compute_pipeline_hash(spec2)

        assert hash1 == hash2

    def test_hash_ignores_parent_hash_change(self):
        """Hash is unchanged when parent_hash changes."""
        spec1 = PipelineSpecDocument(account_id="a", parent_hash=None)
        hash1 = compute_pipeline_hash(spec1)

        spec2 = PipelineSpecDocument(account_id="a", parent_hash="abc123")
        hash2 = compute_pipeline_hash(spec2)

        assert hash1 == hash2

    def test_hash_ignores_version_label_change(self):
        """Hash is unchanged when version_label changes."""
        spec1 = PipelineSpecDocument(account_id="a", version_label="v1")
        hash1 = compute_pipeline_hash(spec1)

        spec2 = PipelineSpecDocument(account_id="a", version_label="custom_label")
        hash2 = compute_pipeline_hash(spec2)

        assert hash1 == hash2

    def test_hash_changes_with_step_config_change(self):
        """Hash changes when step config changes."""
        spec1 = PipelineSpecDocument(
            account_id="a",
            steps=[StepSpec(id="fetch", tool_id="search", config={"top_n": 10})],
        )
        hash1 = compute_pipeline_hash(spec1)

        spec2 = PipelineSpecDocument(
            account_id="a",
            steps=[StepSpec(id="fetch", tool_id="search", config={"top_n": 20})],
        )
        hash2 = compute_pipeline_hash(spec2)

        assert hash1 != hash2


class TestBumpPipelineVersion:
    """Test version bumping logic."""

    def test_bump_no_previous_hash(self):
        """First version bump when no previous hash exists."""
        spec = PipelineSpecDocument(account_id="a")
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(spec, previous_hash=None, revision_repo=mock_repo)

        assert result.version_hash is not None
        assert result.version_seq == 1
        assert result.version_label == "v1"
        mock_repo.save.assert_called_once()

    def test_bump_no_previous_hash_with_existing_seq(self):
        """First bump generates label from seq."""
        spec = PipelineSpecDocument(account_id="a", version_seq=5, version_label=None)
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(spec, previous_hash=None, revision_repo=mock_repo)

        # On first bump (no previous_hash), seq is preserved from spec, label generated
        assert result.version_seq == 5
        assert result.version_label == "v5"

    def test_bump_no_change(self):
        """No bump when hash unchanged and no manual label."""
        # Create an empty spec and compute its actual hash
        spec = PipelineSpecDocument(account_id="a")
        actual_hash = compute_pipeline_hash(spec)
        spec.version_hash = actual_hash
        spec.version_seq = 1
        mock_repo = MagicMock()

        # Pass the same hash as previous_hash
        result = bump_pipeline_version_if_needed(
            spec, previous_hash=actual_hash, revision_repo=mock_repo
        )

        # No change should occur: same hash, no manual label
        assert result.version_hash == actual_hash
        assert result.version_seq == 1
        mock_repo.save.assert_not_called()

    def test_bump_on_hash_change(self):
        """Bump version when hash changes."""
        spec = PipelineSpecDocument(
            account_id="a",
            version_hash="old_hash",
            version_seq=1,
            steps=[StepSpec(id="new", tool_id="t")],
        )
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(
            spec, previous_hash="old_hash", revision_repo=mock_repo
        )

        assert result.version_seq == 2
        assert result.version_label == "v2"
        assert result.version_hash != "old_hash"
        mock_repo.save.assert_called_once()

    def test_bump_with_manual_label(self):
        """Manual label bumps even if hash unchanged."""
        spec = PipelineSpecDocument(
            account_id="a", version_hash="xyz", version_seq=1, version_label="v1"
        )
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(
            spec, previous_hash="xyz", manual_label="release_1.0", revision_repo=mock_repo
        )

        assert result.version_label == "release_1.0"
        mock_repo.save.assert_called_once()

    def test_bump_creates_revision(self):
        """Verify revision is saved on bump."""
        spec = PipelineSpecDocument(account_id="a", steps=[StepSpec(id="s1", tool_id="t1")])
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(spec, previous_hash=None, revision_repo=mock_repo)

        assert mock_repo.save.called
        saved_rev: PipelineRevisionDocument = mock_repo.save.call_args[0][0]
        assert saved_rev.account_id == "a"
        assert saved_rev.seq == 1
        assert saved_rev.version_hash == result.version_hash
        assert len(saved_rev.steps) == 1
        assert saved_rev.steps[0].id == "s1"

    def test_bump_increments_from_existing_seq(self):
        """Bump increments from existing seq when hash changes."""
        spec = PipelineSpecDocument(
            account_id="a",
            version_hash="v1_hash",
            version_seq=3,
            steps=[StepSpec(id="changed", tool_id="t")],
        )
        mock_repo = MagicMock()
        result = bump_pipeline_version_if_needed(
            spec, previous_hash="v1_hash", revision_repo=mock_repo
        )

        assert result.version_seq == 4
        assert result.version_label == "v4"

    def test_bump_whitespace_handling(self):
        """Handle whitespace in hash/label arguments."""
        spec = PipelineSpecDocument(account_id="a")
        # Compute the actual hash of the empty spec
        from app.services.pipeline_version_service import compute_pipeline_hash
        actual_hash = compute_pipeline_hash(spec)
        spec.version_hash = actual_hash
        mock_repo = MagicMock()

        # Whitespace in previous_hash should be stripped
        result = bump_pipeline_version_if_needed(
            spec, previous_hash=f"  {actual_hash}  ", revision_repo=mock_repo
        )
        # Since the stripped hash matches the computed hash, no bump occurs
        mock_repo.save.assert_not_called()

    def test_bump_version_archives_full_snapshot(self):
        """Verify full spec snapshot is archived in revision."""
        spec = PipelineSpecDocument(
            account_id="a",
            steps=[
                StepSpec(id="s1", tool_id="t1", config={"k": "v"}),
            ],
            status="champion",
            parent_hash="parent123",
        )
        mock_repo = MagicMock()
        bump_pipeline_version_if_needed(spec, previous_hash=None, revision_repo=mock_repo)

        saved_rev: PipelineRevisionDocument = mock_repo.save.call_args[0][0]
        assert saved_rev.status == "champion"
        assert saved_rev.parent_hash == "parent123"
        assert len(saved_rev.steps) == 1
        assert saved_rev.steps[0].config == {"k": "v"}

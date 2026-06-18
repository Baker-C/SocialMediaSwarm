"""Tests for outcome ledger attribution model and repository."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.models.outcome_ledger import OutcomeLedgerDocument, compute_reward
from app.services.outcome_ledger_repository import OutcomeLedgerRepository
from app.infrastructure.ravendb_http import RavenDBHttpClient


class TestComputeReward:
    """compute_reward() pure function tests."""

    def test_reward_from_engagement_rate(self) -> None:
        """Reward = engagement_rate when it exists."""
        metrics = {"engagement_rate": 0.05, "impression_count": 1000}
        assert compute_reward(metrics) == 0.05

    def test_reward_none_when_no_engagement_rate(self) -> None:
        """No engagement_rate → reward None."""
        metrics = {"impression_count": 1000}
        assert compute_reward(metrics) is None

    def test_reward_none_for_empty_metrics(self) -> None:
        """Empty metrics dict → reward None."""
        assert compute_reward({}) is None

    def test_reward_none_for_none_metrics(self) -> None:
        """None metrics → reward None."""
        assert compute_reward(None) is None

    def test_reward_zero_when_engagement_rate_is_zero(self) -> None:
        """engagement_rate=0.0 is a valid (zero) reward, not None."""
        metrics = {"engagement_rate": 0.0}
        assert compute_reward(metrics) == 0.0

    def test_reward_coerces_int_to_float(self) -> None:
        """Integer engagement_rate coerced to float."""
        metrics = {"engagement_rate": 1}
        result = compute_reward(metrics)
        assert result == 1.0
        assert isinstance(result, float)

    def test_reward_ignores_other_rates(self) -> None:
        """Reward reads engagement_rate only; ignores reply_rate, like_rate."""
        metrics = {
            "engagement_rate": 0.05,
            "reply_rate": 0.01,
            "like_rate": 0.02,
        }
        assert compute_reward(metrics) == 0.05

    def test_reward_rejects_non_numeric_engagement_rate(self) -> None:
        """Non-numeric engagement_rate → reward None."""
        metrics = {"engagement_rate": "0.05"}
        assert compute_reward(metrics) is None

    def test_reward_ignores_extra_fields(self) -> None:
        """Reward computation ignores unrelated metric fields."""
        metrics = {
            "engagement_rate": 0.05,
            "like_count": 50,
            "impression_count": 1000,
            "unknown_field": "ignored",
        }
        assert compute_reward(metrics) == 0.05


class TestOutcomeLedgerDocument:
    """OutcomeLedgerDocument model tests."""

    def test_document_id_format(self) -> None:
        """Document ID is outcomeledger/{account_id}-{post_id}."""
        doc_id = OutcomeLedgerDocument.document_id("JohnJames_News", "1234567890")
        assert doc_id == "outcomeledger/JohnJames_News-1234567890"

    def test_minimal_document_creation(self) -> None:
        """Minimal required fields: account_id, post_id."""
        doc = OutcomeLedgerDocument(account_id="test", post_id="123")
        assert doc.account_id == "test"
        assert doc.post_id == "123"
        assert doc.run_id is None
        assert doc.soul_hash is None
        assert doc.pipeline_hash is None
        assert doc.reward is None
        assert doc.raw_metrics == {}
        assert doc.recorded_at == ""

    def test_full_document_creation(self) -> None:
        """All fields can be set."""
        now = datetime.now(timezone.utc).isoformat()
        doc = OutcomeLedgerDocument(
            account_id="test_acc",
            post_id="tweet_123",
            run_id="run_abc",
            soul_hash="soul_hash_xyz",
            pipeline_hash="pipeline_hash_123",
            reward=0.03,
            raw_metrics={"impression_count": 1000, "engagement_rate": 0.03},
            recorded_at=now,
        )
        assert doc.account_id == "test_acc"
        assert doc.post_id == "tweet_123"
        assert doc.run_id == "run_abc"
        assert doc.soul_hash == "soul_hash_xyz"
        assert doc.pipeline_hash == "pipeline_hash_123"
        assert doc.reward == 0.03
        assert doc.raw_metrics["engagement_rate"] == 0.03
        assert doc.recorded_at == now

    def test_document_serialization(self) -> None:
        """Document can be serialized to dict."""
        doc = OutcomeLedgerDocument(
            account_id="test",
            post_id="123",
            run_id="run_1",
            reward=0.05,
        )
        data = doc.model_dump(exclude_none=True)
        assert "account_id" in data
        assert "post_id" in data
        assert "run_id" in data
        assert "soul_hash" not in data  # None excluded
        assert data["reward"] == 0.05

    def test_document_deserialization(self) -> None:
        """Document can be deserialized from dict."""
        data = {
            "account_id": "test",
            "post_id": "123",
            "run_id": "run_1",
            "reward": 0.05,
            "recorded_at": "2025-06-18T12:00:00+00:00",
        }
        doc = OutcomeLedgerDocument.model_validate(data)
        assert doc.account_id == "test"
        assert doc.post_id == "123"
        assert doc.run_id == "run_1"
        assert doc.reward == 0.05


class TestOutcomeLedgerRepository:
    """OutcomeLedgerRepository tests (with mocked client)."""

    def test_stamp_creates_new_row(self) -> None:
        """stamp() creates a new OutcomeLedger row at publish time."""
        mock_client = MockRavenDBClient()
        repo = OutcomeLedgerRepository(client=mock_client)

        repo.stamp(
            account_id="test_acc",
            post_id="tweet_123",
            run_id="run_abc",
            soul_hash="soul_hash_xyz",
            pipeline_hash="pipeline_hash_123",
        )

        # Verify put_document was called with correct args
        assert len(mock_client.puts) == 1
        doc_id, data, collection = mock_client.puts[0]
        assert doc_id == "outcomeledger/test_acc-tweet_123"
        assert collection == "OutcomeLedger"
        assert data["account_id"] == "test_acc"
        assert data["post_id"] == "tweet_123"
        assert data["run_id"] == "run_abc"
        assert data["soul_hash"] == "soul_hash_xyz"
        assert data["pipeline_hash"] == "pipeline_hash_123"
        # reward=None is excluded by exclude_none=True, raw_metrics={} is kept
        assert "reward" not in data  # None excluded
        assert data["raw_metrics"] == {}
        assert "recorded_at" in data

    def test_stamp_excludes_none_fields(self) -> None:
        """stamp() serializes with exclude_none=True."""
        mock_client = MockRavenDBClient()
        repo = OutcomeLedgerRepository(client=mock_client)

        repo.stamp(
            account_id="test",
            post_id="123",
            run_id=None,  # Explicitly None
            soul_hash=None,
            pipeline_hash="hash_1",
        )

        doc_id, data, _ = mock_client.puts[0]
        assert "run_id" not in data  # None excluded
        assert "soul_hash" not in data  # None excluded
        assert "pipeline_hash" in data  # Included

    def test_update_outcome_fetches_existing_row(self) -> None:
        """update_outcome() reads the existing row first."""
        mock_client = MockRavenDBClient()
        mock_client.set_document(
            "outcomeledger/test-123",
            {
                "account_id": "test",
                "post_id": "123",
                "run_id": "run_1",
                "reward": None,
                "raw_metrics": {},
            },
        )
        repo = OutcomeLedgerRepository(client=mock_client)

        metrics = {"engagement_rate": 0.05, "impression_count": 1000}
        repo.update_outcome("test", "123", metrics)

        # Verify row was read and then written
        assert len(mock_client.gets) >= 1
        assert len(mock_client.puts) >= 1
        # Verify updated data
        _, data, _ = mock_client.puts[-1]
        assert data["reward"] == 0.05
        assert data["raw_metrics"]["engagement_rate"] == 0.05

    def test_update_outcome_no_op_when_never_stamped(self) -> None:
        """update_outcome() is a silent no-op if the row was never stamped."""
        mock_client = MockRavenDBClient()
        # Document does not exist
        repo = OutcomeLedgerRepository(client=mock_client)

        metrics = {"engagement_rate": 0.05}
        repo.update_outcome("test", "123", metrics)

        # Should have tried to GET the doc
        assert len(mock_client.gets) >= 1
        # Should NOT have created a row (no PUT)
        assert len(mock_client.puts) == 0

    def test_update_outcome_preserves_attribution_header(self) -> None:
        """update_outcome() preserves run_id, soul_hash, pipeline_hash from header."""
        mock_client = MockRavenDBClient()
        mock_client.set_document(
            "outcomeledger/test-123",
            {
                "account_id": "test",
                "post_id": "123",
                "run_id": "run_1",
                "soul_hash": "soul_1",
                "pipeline_hash": "pipe_1",
                "reward": None,
                "raw_metrics": {},
                "recorded_at": "2025-06-18T10:00:00Z",
            },
        )
        repo = OutcomeLedgerRepository(client=mock_client)

        metrics = {"engagement_rate": 0.05}
        repo.update_outcome("test", "123", metrics)

        _, data, _ = mock_client.puts[-1]
        assert data["run_id"] == "run_1"  # Preserved
        assert data["soul_hash"] == "soul_1"  # Preserved
        assert data["pipeline_hash"] == "pipe_1"  # Preserved
        assert data["reward"] == 0.05  # Updated

    def test_update_outcome_updates_recorded_at(self) -> None:
        """update_outcome() updates recorded_at to current time."""
        mock_client = MockRavenDBClient()
        old_time = "2025-06-18T10:00:00Z"
        mock_client.set_document(
            "outcomeledger/test-123",
            {
                "account_id": "test",
                "post_id": "123",
                "recorded_at": old_time,
                "raw_metrics": {},
            },
        )
        repo = OutcomeLedgerRepository(client=mock_client)

        metrics = {"engagement_rate": 0.05}
        repo.update_outcome("test", "123", metrics)

        _, data, _ = mock_client.puts[-1]
        assert data["recorded_at"] != old_time
        # Verify it's ISO format
        assert "T" in data["recorded_at"]
        assert "Z" in data["recorded_at"] or "+00:00" in data["recorded_at"]

    def test_list_for_pipeline_hash_filters_by_hash(self) -> None:
        """list_for_pipeline_hash() queries for given pipeline_hash."""
        mock_client = MockRavenDBClient()
        mock_client.set_query_results([
            {
                "account_id": "test",
                "post_id": "123",
                "pipeline_hash": "pipe_abc",
                "reward": 0.05,
                "raw_metrics": {},
            },
            {
                "account_id": "test",
                "post_id": "456",
                "pipeline_hash": "pipe_abc",
                "reward": 0.03,
                "raw_metrics": {},
            },
        ])
        repo = OutcomeLedgerRepository(client=mock_client)

        results = repo.list_for_pipeline_hash("pipe_abc")

        assert len(results) == 2
        assert all(doc.pipeline_hash == "pipe_abc" for doc in results)
        assert results[0].post_id == "123"
        assert results[1].post_id == "456"

    def test_list_for_pipeline_hash_with_account_filter(self) -> None:
        """list_for_pipeline_hash() can filter by account_id too."""
        mock_client = MockRavenDBClient()
        repo = OutcomeLedgerRepository(client=mock_client)

        repo.list_for_pipeline_hash("pipe_abc", account_id="test")

        # Verify query was made with account_id filter
        query = mock_client.query_text
        assert "account_id" in query
        assert "test" in query

    def test_list_for_pipeline_hash_empty_when_hash_empty(self) -> None:
        """list_for_pipeline_hash() returns [] for empty/invalid hash."""
        repo = OutcomeLedgerRepository()

        results = repo.list_for_pipeline_hash("")
        assert results == []

        results = repo.list_for_pipeline_hash("   ")
        assert results == []

    def test_list_for_pipeline_hash_handles_invalid_rows(self) -> None:
        """list_for_pipeline_hash() skips invalid rows gracefully."""
        mock_client = MockRavenDBClient()
        mock_client.set_query_results([
            {
                "account_id": "test",
                "post_id": "123",
                "pipeline_hash": "pipe_abc",
                "reward": 0.05,
                "raw_metrics": {},
            },
            {
                # Missing required fields — should be skipped
                "account_id": "test",
            },
            {
                "account_id": "test",
                "post_id": "456",
                "pipeline_hash": "pipe_abc",
                "reward": 0.03,
                "raw_metrics": {},
            },
        ])
        repo = OutcomeLedgerRepository(client=mock_client)

        results = repo.list_for_pipeline_hash("pipe_abc")

        # Should have 2 valid rows (the 3rd was skipped)
        assert len(results) == 2


class MockRavenDBClient:
    """Mock RavenDB client for testing."""

    def __init__(self) -> None:
        self.puts: list[tuple[str, dict, str]] = []
        self.gets: list[str] = []
        self.documents: dict[str, dict] = {}
        self.query_results: list[dict] = []
        self.query_text: str = ""

    def put_document(self, doc_id: str, data: dict, collection: str) -> None:
        self.puts.append((doc_id, data, collection))
        self.documents[doc_id] = data

    def get_document(self, doc_id: str) -> dict | None:
        self.gets.append(doc_id)
        return self.documents.get(doc_id)

    def query(self, rql: str) -> list[dict]:
        self.query_text = rql
        return self.query_results

    def set_document(self, doc_id: str, data: dict) -> None:
        """Helper to set up test data."""
        self.documents[doc_id] = data

    def set_query_results(self, results: list[dict]) -> None:
        """Helper to set up query results."""
        self.query_results = results


# Integration-style tests (assume minimal RavenDB setup available)
class TestPostCreationMetricsIntegration:
    """Tests for PostCreationMetrics model additions."""

    def test_creation_metrics_new_fields_optional(self) -> None:
        """New run_id and pipeline_hash fields are optional."""
        from app.models.tracked_post import PostCreationMetrics

        # Should construct without the new fields
        metrics = PostCreationMetrics(
            candidates_created=1,
            voice_version_hash="voice_1",
        )
        assert metrics.run_id is None
        assert metrics.pipeline_hash is None

    def test_creation_metrics_with_new_fields(self) -> None:
        """New fields can be set."""
        from app.models.tracked_post import PostCreationMetrics

        metrics = PostCreationMetrics(
            candidates_created=1,
            voice_version_hash="voice_1",
            run_id="run_abc",
            pipeline_hash="pipe_xyz",
        )
        assert metrics.run_id == "run_abc"
        assert metrics.pipeline_hash == "pipe_xyz"

    def test_creation_metrics_serialization_excludes_none(self) -> None:
        """Serialization with exclude_none=True omits None fields."""
        from app.models.tracked_post import PostCreationMetrics

        metrics = PostCreationMetrics(
            candidates_created=1,
            run_id="run_abc",
            pipeline_hash=None,
        )
        data = metrics.model_dump(exclude_none=True)
        assert "run_id" in data
        assert "pipeline_hash" not in data

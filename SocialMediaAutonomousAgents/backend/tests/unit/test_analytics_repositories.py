"""Unit tests for analytics repository list methods."""

from unittest.mock import MagicMock

from app.models.pipeline_outcome import PipelineOutcomeDocument
from app.models.post_metric_snapshot import PostMetricSnapshotDocument
from app.models.voice_revision import VoiceRevisionDocument
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.post_metric_snapshot_repository import PostMetricSnapshotRepository
from app.services.post_registry import TrackedPostRepository
from app.services.voice_revision_repository import VoiceRevisionRepository


def test_post_metric_snapshot_list_for_tweet_orders_asc() -> None:
    client = MagicMock()
    client.query.return_value = [
        {"account_id": "a1", "tweet_id": "t1", "captured_at": "2026-06-01T00:00:00+00:00"},
        {"account_id": "a1", "tweet_id": "t1", "captured_at": "2026-06-02T00:00:00+00:00"},
    ]
    repo = PostMetricSnapshotRepository(client=client)

    rows = repo.list_for_tweet("a1", "t1", limit=100)

    assert len(rows) == 2
    assert all(isinstance(r, PostMetricSnapshotDocument) for r in rows)
    rql = client.query.call_args[0][0]
    assert "order by captured_at asc" in rql
    assert 'account_id == "a1"' in rql
    assert 'tweet_id == "t1"' in rql


def test_pipeline_outcome_list_for_account_filters() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "acct1",
            "phase": "runner",
            "status": "skipped",
            "created_at": "2026-06-08T10:00:00+00:00",
            "reason": "cooldown",
        },
        {
            "account_id": "acct1",
            "phase": "runner",
            "status": "success",
            "created_at": "2026-06-01T10:00:00+00:00",
        },
    ]
    repo = PipelineOutcomeRepository(client=client)

    rows = repo.list_for_account(
        "acct1",
        since="2026-06-05T00:00:00+00:00",
        limit=50,
        phase="runner",
        status="skipped",
    )

    assert len(rows) == 1
    assert rows[0].reason == "cooldown"
    rql = client.query.call_args[0][0]
    assert "order by created_at desc" in rql
    assert 'account_id == "acct1"' in rql


def test_pipeline_outcome_list_fleet_optional_account_filter() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "a1",
            "phase": "runner",
            "status": "success",
            "created_at": "2026-06-08T12:00:00+00:00",
        },
        {
            "account_id": "a2",
            "phase": "runner",
            "status": "success",
            "created_at": "2026-06-08T11:00:00+00:00",
        },
    ]
    repo = PipelineOutcomeRepository(client=client)

    all_rows = repo.list_fleet(limit=10)
    assert len(all_rows) == 2

    filtered = repo.list_fleet(limit=10, account_id="a1")
    assert len(filtered) == 1
    assert filtered[0].account_id == "a1"


def test_voice_revision_list_for_account_orders_by_seq() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "acct1",
            "seq": 1,
            "label": "v1",
            "version_hash": "h1",
            "changed_at": "2026-06-01T00:00:00+00:00",
        },
        {
            "account_id": "acct1",
            "seq": 2,
            "label": "v2",
            "version_hash": "h2",
            "changed_at": "2026-06-02T00:00:00+00:00",
        },
    ]
    repo = VoiceRevisionRepository(client=client)

    rows = repo.list_for_account("acct1")

    assert len(rows) == 2
    assert all(isinstance(r, VoiceRevisionDocument) for r in rows)
    rql = client.query.call_args[0][0]
    assert "order by seq asc" in rql


def test_tracked_post_list_for_account_since_filter() -> None:
    client = MagicMock()
    client.query.return_value = [
        {"account_id": "a1", "tweet_id": "old", "posted_at": "2026-05-01T00:00:00+00:00"},
        {"account_id": "a1", "tweet_id": "new", "posted_at": "2026-06-08T00:00:00+00:00"},
    ]
    repo = TrackedPostRepository(client=client)

    rows = repo.list_for_account("a1", since="2026-06-01T00:00:00+00:00", limit=500)

    assert len(rows) == 1
    assert rows[0]["tweet_id"] == "new"

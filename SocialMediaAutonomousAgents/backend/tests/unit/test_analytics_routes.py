"""Analytics API route tests."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.pipeline_outcome import PipelineOutcomeDocument
from app.models.post_metric_snapshot import PostMetricSnapshotDocument
from app.models.tracked_post import TrackedPostDocument
from app.models.voice_revision import VoiceRevisionDocument


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@patch("app.api.routes.analytics.repo")
def test_tracked_posts_404_unknown_account(mock_repo, client: TestClient) -> None:
    mock_repo.load.return_value = None
    resp = client.get("/api/accounts/missing/tracked-posts")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_tracked_posts_returns_rows(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.list_for_account.return_value = [
        {"account_id": "acct1", "tweet_id": "99", "posted_at": "2026-06-08T00:00:00+00:00"}
    ]

    resp = client.get("/api/accounts/acct1/tracked-posts?limit=10&since=2026-06-01T00:00:00Z")

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == "acct1"
    assert body["count"] == 1
    assert body["posts"][0]["tweet_id"] == "99"
    mock_tracked.list_for_account.assert_called_once_with(
        "acct1", limit=10, since="2026-06-01T00:00:00Z"
    )


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_get_tracked_post_404(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.get_for_tweet.return_value = None
    resp = client.get("/api/accounts/acct1/posts/missing")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_get_tracked_post_returns_document(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.get_for_tweet.return_value = TrackedPostDocument(
        account_id="acct1",
        tweet_id="99",
        posted_at="2026-06-08T00:00:00+00:00",
    ).model_dump()

    resp = client.get("/api/accounts/acct1/posts/99")
    assert resp.status_code == 200
    assert resp.json()["tweet_id"] == "99"


@patch("app.api.routes.analytics.post_snapshots")
@patch("app.api.routes.analytics.repo")
def test_post_snapshots_returns_rows(mock_repo, mock_snapshots, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_snapshots.list_for_tweet.return_value = [
        PostMetricSnapshotDocument(
            account_id="acct1",
            tweet_id="99",
            captured_at="2026-06-08T01:00:00+00:00",
        )
    ]

    resp = client.get("/api/accounts/acct1/posts/99/snapshots?limit=50")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tweet_id"] == "99"
    assert body["count"] == 1
    mock_snapshots.list_for_tweet.assert_called_once_with("acct1", "99", limit=50)


@patch("app.api.routes.analytics.service")
@patch("app.api.routes.analytics.repo")
def test_account_metrics_404(mock_repo, mock_service, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_service.get_account_metrics.return_value = None
    resp = client.get("/api/accounts/acct1/account-metrics")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.service")
@patch("app.api.routes.analytics.repo")
def test_account_metrics_returns_doc(mock_repo, mock_service, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_service.get_account_metrics.return_value = {
        "account_id": "acct1",
        "computed_at": "2026-06-08T00:00:00+00:00",
        "avg_reply_rate": 0.05,
    }
    resp = client.get("/api/accounts/acct1/account-metrics")
    assert resp.status_code == 200
    assert resp.json()["avg_reply_rate"] == 0.05


@patch("app.api.routes.analytics.pipeline_outcomes")
@patch("app.api.routes.analytics.repo")
def test_pipeline_outcomes_for_account(mock_repo, mock_outcomes, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_outcomes.list_for_account.return_value = [
        PipelineOutcomeDocument(
            account_id="acct1",
            phase="runner",
            status="skipped",
            created_at="2026-06-08T00:00:00+00:00",
            reason="cooldown",
        )
    ]

    resp = client.get("/api/accounts/acct1/pipeline-outcomes?phase=runner&status=skipped")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["outcomes"][0]["reason"] == "cooldown"


@patch("app.api.routes.analytics.voice_revisions")
@patch("app.api.routes.analytics.repo")
def test_voice_revisions_for_account(mock_repo, mock_voice, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_voice.list_for_account.return_value = [
        VoiceRevisionDocument(
            account_id="acct1",
            seq=1,
            label="v1",
            version_hash="abc",
            changed_at="2026-06-01T00:00:00+00:00",
        )
    ]

    resp = client.get("/api/accounts/acct1/voice-revisions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["revisions"][0]["label"] == "v1"


@patch("app.api.routes.analytics.pipeline_outcomes")
def test_fleet_pipeline_outcomes(mock_outcomes, client: TestClient) -> None:
    mock_outcomes.list_fleet.return_value = [
        PipelineOutcomeDocument(
            account_id="a1",
            phase="runner",
            status="success",
            created_at="2026-06-08T00:00:00+00:00",
        ),
        PipelineOutcomeDocument(
            account_id="a2",
            phase="engagement_job",
            status="partial_or_failed",
            created_at="2026-06-07T00:00:00+00:00",
        ),
    ]

    resp = client.get("/api/pipeline-outcomes?limit=100&since=2026-06-01T00:00:00Z")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    mock_outcomes.list_fleet.assert_called_once_with(
        since="2026-06-01T00:00:00Z",
        limit=100,
        account_id=None,
        phase=None,
        status=None,
    )


@patch("app.api.routes.analytics.pipeline_outcomes")
@patch("app.api.routes.analytics.repo")
def test_fleet_pipeline_outcomes_with_account_filter(mock_repo, mock_outcomes, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_outcomes.list_fleet.return_value = []

    resp = client.get("/api/pipeline-outcomes?account_id=acct1")

    assert resp.status_code == 200
    mock_outcomes.list_fleet.assert_called_once_with(
        since=None,
        limit=200,
        account_id="acct1",
        phase=None,
        status=None,
    )


@patch("app.api.routes.analytics.repo")
def test_fleet_pipeline_outcomes_404_unknown_account(mock_repo, client: TestClient) -> None:
    mock_repo.load.return_value = None
    resp = client.get("/api/pipeline-outcomes?account_id=missing")
    assert resp.status_code == 404

"""Analytics read API routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.metrics import AccountMetricsDocument
from app.models.pipeline_outcome import PipelineOutcomeDocument
from app.models.post_metric_snapshot import PostMetricSnapshotDocument
from app.models.voice_revision import VoiceRevisionDocument


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_list_tracked_posts(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.list_for_account.return_value = [
        {"account_id": "acct1", "tweet_id": "99", "posted_at": "t0"}
    ]

    resp = client.get("/api/accounts/acct1/tracked-posts?limit=10&since=2026-06-01")

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == "acct1"
    assert body["count"] == 1
    assert body["posts"][0]["tweet_id"] == "99"
    mock_tracked.list_for_account.assert_called_once_with(
        "acct1", limit=10, since="2026-06-01"
    )


@patch("app.api.routes.analytics.repo")
def test_list_tracked_posts_404(mock_repo, client: TestClient) -> None:
    mock_repo.load.return_value = None
    resp = client.get("/api/accounts/missing/tracked-posts")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_get_tracked_post(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.get_for_tweet.return_value = {
        "account_id": "acct1",
        "tweet_id": "99",
        "posted_at": "t0",
    }

    resp = client.get("/api/accounts/acct1/posts/99")

    assert resp.status_code == 200
    assert resp.json()["tweet_id"] == "99"


@patch("app.api.routes.analytics.tracked_posts")
@patch("app.api.routes.analytics.repo")
def test_get_tracked_post_404(mock_repo, mock_tracked, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_tracked.get_for_tweet.return_value = None
    resp = client.get("/api/accounts/acct1/posts/missing")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.post_snapshots")
@patch("app.api.routes.analytics.repo")
def test_list_post_snapshots(mock_repo, mock_snapshots, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_snapshots.list_for_tweet.return_value = [
        PostMetricSnapshotDocument(
            account_id="acct1",
            tweet_id="99",
            captured_at="t0",
            like_count=1,
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
def test_get_account_metrics(mock_repo, mock_service, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_service.get_account_metrics.return_value = AccountMetricsDocument(
        account_id="acct1",
        computed_at="t0",
        avg_engagement_rate=0.05,
        avg_reply_rate=0.01,
    ).model_dump(exclude_none=True)

    resp = client.get("/api/accounts/acct1/account-metrics")

    assert resp.status_code == 200
    assert resp.json()["avg_reply_rate"] == 0.01


@patch("app.api.routes.analytics.service")
@patch("app.api.routes.analytics.repo")
def test_get_account_metrics_404(mock_repo, mock_service, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_service.get_account_metrics.return_value = None
    resp = client.get("/api/accounts/acct1/account-metrics")
    assert resp.status_code == 404


@patch("app.api.routes.analytics.pipeline_outcomes")
@patch("app.api.routes.analytics.repo")
def test_list_pipeline_outcomes(mock_repo, mock_outcomes, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_outcomes.list_for_account.return_value = [
        PipelineOutcomeDocument(
            account_id="acct1",
            phase="runner",
            status="ok",
            created_at="t0",
        )
    ]

    resp = client.get(
        "/api/accounts/acct1/pipeline-outcomes?limit=20&phase=runner&status=ok&since=2026-06-01"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["outcomes"][0]["phase"] == "runner"
    mock_outcomes.list_for_account.assert_called_once_with(
        "acct1", since="2026-06-01", limit=20, phase="runner", status="ok"
    )


@patch("app.api.routes.analytics.voice_revisions")
@patch("app.api.routes.analytics.repo")
def test_list_voice_revisions(mock_repo, mock_revisions, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_revisions.list_for_account.return_value = [
        VoiceRevisionDocument(
            account_id="acct1",
            seq=1,
            label="v1",
            version_hash="h1",
            changed_at="t0",
        )
    ]

    resp = client.get("/api/accounts/acct1/voice-revisions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["revisions"][0]["label"] == "v1"

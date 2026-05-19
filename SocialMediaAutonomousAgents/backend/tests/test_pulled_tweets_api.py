"""GET /api/accounts/{account_id}/pulled-tweets."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.pulled_tweet import PulledTweetDocument


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@patch("app.api.routes.accounts.pulled_tweets")
@patch("app.api.routes.accounts.repo")
def test_list_pulled_tweets_returns_rows(mock_repo, mock_pulled, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_pulled.list_for_account.return_value = [
        PulledTweetDocument(
            tweet_id="99",
            text="hello",
            first_pulled_at="t0",
            last_pulled_at="t1",
            first_pulled_for_account_id="acct1",
            last_pulled_for_account_id="acct1",
            pulled_for_account_ids=["acct1"],
        )
    ]

    resp = client.get("/api/accounts/acct1/pulled-tweets?limit=10")

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == "acct1"
    assert body["count"] == 1
    assert body["tweets"][0]["tweet_id"] == "99"
    mock_pulled.list_for_account.assert_called_once_with("acct1", limit=10, since=None)


@patch("app.api.routes.accounts.repo")
def test_list_pulled_tweets_404_unknown_account(mock_repo, client: TestClient) -> None:
    mock_repo.load.return_value = None
    resp = client.get("/api/accounts/missing/pulled-tweets")
    assert resp.status_code == 404


@patch("app.api.routes.accounts.pulled_tweets")
@patch("app.api.routes.accounts.repo")
def test_list_pulled_tweets_empty(mock_repo, mock_pulled, client: TestClient) -> None:
    mock_repo.load.return_value = MagicMock(account_id="acct1")
    mock_pulled.list_for_account.return_value = []
    resp = client.get("/api/accounts/acct1/pulled-tweets")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["tweets"] == []

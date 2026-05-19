from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes import accounts as accounts_routes
from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_accounts():
    response = client.get("/api/accounts")
    assert response.status_code == 200


def test_account_edit_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = None
    monkeypatch.setattr(accounts_routes, "repo", mock_repo)
    response = client.get("/api/accounts/missing/edit")
    assert response.status_code == 404


def test_account_patch_oauth1_partial_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.account import AccountDocument

    mock_repo = MagicMock()
    mock_repo.load.return_value = AccountDocument(
        account_id="u",
        niche="n",
        twitter_handle="",
        status="active",
    )
    monkeypatch.setattr(accounts_routes, "repo", mock_repo)
    response = client.patch(
        "/api/accounts/u",
        json={"twitter_api_key": "only-one"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "detail" in body

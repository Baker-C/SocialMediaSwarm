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


def test_account_patch_ignores_removed_oauth1_fields(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert response.status_code == 200


def test_account_create_conflict_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.account import AccountDocument

    mock_repo = MagicMock()
    mock_repo.load.return_value = AccountDocument(
        account_id="taken",
        niche="n",
        twitter_handle="",
        status="active",
    )
    monkeypatch.setattr(accounts_routes, "repo", mock_repo)
    response = client.post(
        "/api/accounts",
        json={"account_id": "taken", "twitter_oauth2_access_token": "tok"},
    )
    assert response.status_code == 409


def test_account_create_missing_credentials_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = None
    monkeypatch.setattr(accounts_routes, "repo", mock_repo)
    response = client.post("/api/accounts", json={"account_id": "new"})
    assert response.status_code == 400


def test_account_create_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.account import AccountDocument

    created = AccountDocument(
        account_id="new",
        niche="niche",
        twitter_handle="@n",
        status="active",
        twitter_oauth2_access_token_enc="enc",
    )
    mock_repo = MagicMock()
    mock_repo.load.return_value = None
    monkeypatch.setattr(accounts_routes, "repo", mock_repo)
    monkeypatch.setattr(
        accounts_routes,
        "apply_account_create",
        MagicMock(return_value=created),
    )
    response = client.post(
        "/api/accounts",
        json={"account_id": "new", "twitter_oauth2_access_token": "tok"},
    )
    assert response.status_code == 201
    assert response.json() == {"ok": True, "account_id": "new"}

"""OAuth API route error responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import oauth as oauth_routes
from app.main import app


client = TestClient(app)


def test_oauth_callback_access_denied_user_friendly(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the API-error fallback path (no frontend redirect base configured).
    monkeypatch.setattr(oauth_routes, "_frontend_redirect", lambda **kw: None)
    response = client.get(
        "/api/oauth/x/callback",
        params={"error": "access_denied", "error_description": "User cancelled"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "cancelled" in detail or "denied" in detail


def test_oauth_callback_missing_code_or_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_routes, "_frontend_redirect", lambda **kw: None)
    response = client.get("/api/oauth/x/callback", params={"code": "", "state": ""})
    assert response.status_code == 400
    assert "restart" in response.json()["detail"].lower()


def test_oauth_callback_exchange_invalid_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_routes, "_frontend_redirect", lambda **kw: None)
    mock_svc = MagicMock()
    mock_svc.exchange_authorization_code.side_effect = ValueError(
        "Authorization code expired or already used. Please restart X connection."
    )
    monkeypatch.setattr(oauth_routes, "oauth_service", mock_svc)
    response = client.get(
        "/api/oauth/x/callback",
        params={"code": "c", "state": "s"},
    )
    assert response.status_code == 400
    assert "restart" in response.json()["detail"].lower()


def test_oauth_callback_redirect_carries_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oauth_routes.settings, "twitter_oauth2_success_redirect_url", "https://app.example.com/oauth"
    )
    mock_svc = MagicMock()
    mock_svc.exchange_authorization_code.return_value = MagicMock(
        account_id="aid-1", x_user_id="uid-1", x_username="alice", expires_at="x", scopes="s"
    )
    monkeypatch.setattr(oauth_routes, "oauth_service", mock_svc)

    response = client.get(
        "/api/oauth/x/callback", params={"code": "c", "state": "s"}, follow_redirects=False
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "x_username=alice" in location
    assert "connected=1" in location
    assert "unverified" not in location


def test_oauth_callback_rejection_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_routes, "_frontend_redirect", lambda **kw: None)
    mock_svc = MagicMock()
    mock_svc.exchange_authorization_code.side_effect = ValueError(
        "This X account (@bob) is already connected to account 'aid-existing'. "
        "Each dashboard account must use a distinct X account."
    )
    monkeypatch.setattr(oauth_routes, "oauth_service", mock_svc)
    response = client.get("/api/oauth/x/callback", params={"code": "c", "state": "s"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "aid-existing" in detail
    assert "@bob" in detail

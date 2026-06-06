"""OAuth API route error responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import oauth as oauth_routes
from app.main import app


client = TestClient(app)


def test_oauth_callback_access_denied_user_friendly() -> None:
    response = client.get(
        "/api/oauth/x/callback",
        params={"error": "access_denied", "error_description": "User cancelled"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "cancelled" in detail or "denied" in detail


def test_oauth_callback_missing_code_or_state() -> None:
    response = client.get("/api/oauth/x/callback", params={"code": "", "state": ""})
    assert response.status_code == 400
    assert "restart" in response.json()["detail"].lower()


def test_oauth_callback_exchange_invalid_grant(monkeypatch: pytest.MonkeyPatch) -> None:
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

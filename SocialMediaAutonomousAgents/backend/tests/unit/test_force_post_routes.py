"""Force-post API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.routes import force_post as force_post_routes
from app.main import app
from app.models.account import AccountDocument

client = TestClient(app)


def test_force_post_404_unknown_account(monkeypatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = None
    monkeypatch.setattr(force_post_routes, "repo", mock_repo)
    response = client.post("/api/accounts/missing/force-post")
    assert response.status_code == 404


def test_force_post_json(monkeypatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = AccountDocument(
        account_id="acct1",
        niche="news",
        status="active",
    )
    monkeypatch.setattr(force_post_routes, "repo", mock_repo)

    with patch.object(force_post_routes, "run_force_post", return_value={"slot": "s1", "results": []}):
        response = client.post("/api/accounts/acct1/force-post")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"]["slot"] == "s1"


def test_force_post_json_reports_pipeline_failure(monkeypatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = AccountDocument(
        account_id="acct1",
        niche="news",
        status="active",
    )
    monkeypatch.setattr(force_post_routes, "repo", mock_repo)

    with patch.object(
        force_post_routes,
        "run_force_post",
        return_value={"slot": "s1", "results": [{"account_id": "acct1", "skipped": "no_oauth_tokens"}]},
    ):
        response = client.post("/api/accounts/acct1/force-post")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["failure"] == "no_oauth_tokens"


def test_force_post_sse_progress(monkeypatch) -> None:
    mock_repo = MagicMock()
    mock_repo.load.return_value = AccountDocument(
        account_id="acct1",
        niche="news",
        status="active",
    )
    monkeypatch.setattr(force_post_routes, "repo", mock_repo)

    def fake_run(account_id: str, *, on_progress=None, bypass_cooldown=True):
        assert account_id == "acct1"
        if on_progress:
            on_progress("load_account", "Loading account", "active")
            on_progress("load_account", "Loading account", "done")
        return {"slot": "s1", "results": [{"account_id": "acct1", "posted": True}]}

    with patch.object(force_post_routes, "run_force_post", side_effect=fake_run):
        response = client.post(
            "/api/accounts/acct1/force-post",
            headers={"Accept": "text/event-stream"},
        )
    assert response.status_code == 200
    text = response.text
    assert "progress" in text
    assert "load_account" in text
    assert "complete" in text

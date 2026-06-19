"""Provisioning routes: two trust domains (dashboard auth vs agent token)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import provisioning as provisioning_routes
from app.api.routes.provisioning_types import ProvisioningJob
from app.main import app

client = TestClient(app)


def test_start_404_unknown(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.svc, "start", _raise(LookupError("aid")))
    r = client.post("/api/provisioning/aid/start")
    assert r.status_code == 404


def test_start_409_already(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.svc, "start", _raise(ValueError("already provisioning")))
    r = client.post("/api/provisioning/aid/start")
    assert r.status_code == 409


def test_start_202(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.svc, "start", lambda aid: None)
    r = client.post("/api/provisioning/aid/start")
    assert r.status_code == 202
    assert r.json() == {"ok": True}


def test_agent_job_401_without_token(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    r = client.get("/api/provisioning/aid/job")
    assert r.status_code == 401


def test_agent_job_200_with_token(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    monkeypatch.setattr(
        provisioning_routes.svc,
        "build_job",
        lambda aid: ProvisioningJob(
            account_id=aid, handle="h", display_name="n", bio="b",
            avatar_asset_id=None, header_asset_id=None, email="e@x.y",
        ),
    )
    r = client.get("/api/provisioning/aid/job", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json()["email"] == "e@x.y"


def test_agent_token_blank_rejects_even_blank_bearer(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "")
    r = client.get("/api/provisioning/aid/job", headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_control_set_then_poll_returns_and_clears(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    # frontend sets the flag (no agent token needed)
    r = client.post("/api/provisioning/aid/control", json={"action": "continue"})
    assert r.status_code == 200

    # agent polls: returns it, then clears
    headers = {"Authorization": "Bearer t"}
    r1 = client.get("/api/provisioning/aid/control", headers=headers)
    assert r1.status_code == 200
    assert r1.json() == {"action": "continue"}
    r2 = client.get("/api/provisioning/aid/control", headers=headers)
    assert r2.json() == {"action": ""}


def _raise(exc: Exception):
    def _fn(aid: str):
        raise exc
    return _fn

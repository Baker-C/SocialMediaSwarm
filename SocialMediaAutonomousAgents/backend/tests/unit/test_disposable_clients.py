"""Disposable identity: email + SIM-phone clients and agent endpoints (sync only)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import app.infrastructure.disposable_email_client as email_mod
import app.infrastructure.disposable_phone_client as phone_mod
from app.api.routes import provisioning as provisioning_routes
from app.infrastructure.disposable_email_client import (
    DisposableEmailClient,
    DisposableEmailError,
)
from app.infrastructure.disposable_phone_client import (
    DisposablePhoneClient,
    DisposablePhoneError,
    PhoneLease,
)
from app.main import app

client = TestClient(app)


# ── email client (n8n Mailgun workflows) ──

def test_create_inbox_calls_n8n_webhook(monkeypatch) -> None:
    """Email inbox creation via n8n acquire-email webhook."""
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        mock_resp = ClientCls.return_value.__enter__.return_value.post.return_value
        mock_resp.json.return_value = {"email": "test-abc@xswarm.mailgun.org"}
        mock_resp.raise_for_status.return_value = None
        addr = c.create_inbox("test-account")
        assert addr == "test-abc@xswarm.mailgun.org"


def test_create_inbox_raises_on_error(monkeypatch) -> None:
    """Email inbox creation fails if n8n workflow errors."""
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.post.side_effect = Exception("n8n error")
        with pytest.raises(DisposableEmailError, match="n8n create_inbox failed"):
            c.create_inbox("aid")


def test_email_fetch_code_parses_six_digits(monkeypatch) -> None:
    """Email code fetching via n8n fetch-email-code webhook."""
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        mock_resp = ClientCls.return_value.__enter__.return_value.get.return_value
        mock_resp.json.return_value = {"code": "123456"}
        mock_resp.raise_for_status.return_value = None
        assert c.fetch_code("a@mail.example.com", timeout_s=0) == "123456"


def test_email_fetch_code_returns_none_on_no_match(monkeypatch) -> None:
    """Email code fetch returns None if no code found."""
    from unittest.mock import MagicMock
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        mock_get = ClientCls.return_value.__enter__.return_value.get
        # First call: no code, Second call: has code
        resp1 = MagicMock()
        resp1.json.return_value = {"code": None}
        resp1.raise_for_status.return_value = None
        resp2 = MagicMock()
        resp2.json.return_value = {"code": "654321"}
        resp2.raise_for_status.return_value = None
        mock_get.side_effect = [resp1, resp2]
        assert c.fetch_code("a@mail.example.com", timeout_s=30) == "654321"


def test_email_fetch_code_timeout_returns_none(monkeypatch) -> None:
    """Email code fetch returns None on timeout."""
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        mock_resp = ClientCls.return_value.__enter__.return_value.get.return_value
        mock_resp.json.return_value = {"code": None}
        mock_resp.raise_for_status.return_value = None
        assert c.fetch_code("a@mail.example.com", timeout_s=0) is None


# ── phone client (n8n Vonage workflows) ──

def test_phone_acquire_returns_lease(monkeypatch) -> None:
    """Phone acquisition via n8n acquire-phone webhook."""
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        mock_resp = ClientCls.return_value.__enter__.return_value.post.return_value
        mock_resp.json.return_value = {"lease_id": "lease-9", "phone": "+15551234567"}
        mock_resp.raise_for_status.return_value = None
        lease = c.acquire_number()
    assert isinstance(lease, PhoneLease)
    assert lease.lease_id == "lease-9"
    assert lease.phone == "+15551234567"


def test_phone_acquire_error_response_raises(monkeypatch) -> None:
    """Phone acquisition fails if n8n workflow errors."""
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.post.side_effect = Exception("n8n error")
        with pytest.raises(DisposablePhoneError, match="n8n acquire_phone failed"):
            c.acquire_number()


def test_phone_fetch_code_parses(monkeypatch) -> None:
    """Phone code fetching via n8n fetch-sms webhook."""
    monkeypatch.setattr(phone_mod.time, "sleep", lambda *_: None)
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        mock_resp = ClientCls.return_value.__enter__.return_value.get.return_value
        mock_resp.json.return_value = {"code": "222333"}
        mock_resp.raise_for_status.return_value = None
        assert c.fetch_code("lease-9", timeout_s=0) == "222333"


# ── endpoints ──

class _FakeSecrets:
    def __init__(self, email: str | None = None) -> None:
        from app.services.account_secrets_service import AccountSecrets

        self._sec = AccountSecrets(account_id="aid", disposable_email=email) if email else None
        self.upserts: list[dict] = []

    def get(self, account_id: str):
        return self._sec

    def upsert(self, account_id: str, **fields):
        self.upserts.append({"account_id": account_id, **fields})


def test_email_code_endpoint_401_without_token(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    r = client.get("/api/provisioning/aid/email-code")
    assert r.status_code == 401


def test_email_code_endpoint_returns_code(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    monkeypatch.setattr(provisioning_routes, "secrets_svc", _FakeSecrets(email="a@mail.example.com"))

    class _Email:
        def fetch_code(self, address, **kw):
            return "987654"

    monkeypatch.setattr(provisioning_routes, "get_disposable_email_client", lambda: _Email())
    r = client.get("/api/provisioning/aid/email-code", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"code": "987654"}


def test_phone_endpoint_401_without_token(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    r = client.post("/api/provisioning/aid/phone")
    assert r.status_code == 401


def test_phone_endpoint_persists_number(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    fake = _FakeSecrets()
    monkeypatch.setattr(provisioning_routes, "secrets_svc", fake)

    class _Phone:
        def acquire_number(self, **kw):
            return PhoneLease(lease_id="L1", phone="+15550001111")

    monkeypatch.setattr(provisioning_routes, "get_disposable_phone_client", lambda: _Phone())
    r = client.post("/api/provisioning/aid/phone", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"phone": "+15550001111", "lease_id": "L1"}
    assert fake.upserts == [{"account_id": "aid", "disposable_phone": "+15550001111"}]
    assert provisioning_routes._phone_leases.get("aid") == "L1"


def test_phone_code_endpoint_uses_stored_lease(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    provisioning_routes._phone_leases["aid"] = "L9"

    class _Phone:
        def fetch_code(self, lease_id, **kw):
            assert lease_id == "L9"
            return "445566"

    monkeypatch.setattr(provisioning_routes, "get_disposable_phone_client", lambda: _Phone())
    r = client.get("/api/provisioning/aid/phone-code", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"code": "445566"}

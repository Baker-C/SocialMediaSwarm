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


# ── email client ──

def test_create_inbox_returns_address_on_domain(monkeypatch) -> None:
    monkeypatch.setattr(email_mod.settings, "disposable_email_domain", "mail.example.com")
    addr = DisposableEmailClient().create_inbox("Acct-123")
    assert addr.endswith("@mail.example.com")
    assert addr.startswith("acct123-")


def test_create_inbox_requires_domain(monkeypatch) -> None:
    monkeypatch.setattr(email_mod.settings, "disposable_email_domain", "")
    with pytest.raises(DisposableEmailError):
        DisposableEmailClient().create_inbox("aid")


def test_email_fetch_code_parses_six_digits(monkeypatch) -> None:
    monkeypatch.setattr(email_mod.settings, "disposable_email_api_base", "https://mb.example")
    resp = httpx.Response(200, json={"messages": [{"subject": "Verify", "text": "Your code is 123456 now"}]})
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.get.return_value = resp
        assert c.fetch_code("a@mail.example.com", timeout_s=0) == "123456"


def test_email_fetch_code_returns_none_on_no_match(monkeypatch) -> None:
    monkeypatch.setattr(email_mod.settings, "disposable_email_api_base", "https://mb.example")
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    empty = httpx.Response(200, json={"messages": []})
    hit = httpx.Response(200, json={"messages": [{"text": "code 654321"}]})
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        # First poll empty, second poll has the code (simulate polling via side_effect).
        ClientCls.return_value.__enter__.return_value.get.side_effect = [empty, hit]
        assert c.fetch_code("a@mail.example.com", timeout_s=30) == "654321"


def test_email_fetch_code_timeout_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(email_mod.settings, "disposable_email_api_base", "https://mb.example")
    empty = httpx.Response(200, json={"messages": [{"text": "no digits here"}]})
    c = DisposableEmailClient()
    with patch("app.infrastructure.disposable_email_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.get.return_value = empty
        assert c.fetch_code("a@mail.example.com", timeout_s=0) is None


# ── phone client ──

def test_phone_acquire_returns_lease(monkeypatch) -> None:
    monkeypatch.setattr(phone_mod.settings, "disposable_phone_api_base", "https://sim.example")
    resp = httpx.Response(200, json={"id": "lease-9", "phone": "+15551234567"})
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.get.return_value = resp
        lease = c.acquire_number()
    assert isinstance(lease, PhoneLease)
    assert lease.lease_id == "lease-9"
    assert lease.phone == "+15551234567"


def test_phone_acquire_error_response_raises(monkeypatch) -> None:
    monkeypatch.setattr(phone_mod.settings, "disposable_phone_api_base", "https://sim.example")
    resp = httpx.Response(503, text="no numbers available")
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.get.return_value = resp
        with pytest.raises(DisposablePhoneError):
            c.acquire_number()


def test_phone_fetch_code_parses(monkeypatch) -> None:
    monkeypatch.setattr(phone_mod.settings, "disposable_phone_api_base", "https://sim.example")
    resp = httpx.Response(200, json={"sms": "X code: 222333"})
    c = DisposablePhoneClient()
    with patch("app.infrastructure.disposable_phone_client.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.get.return_value = resp
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

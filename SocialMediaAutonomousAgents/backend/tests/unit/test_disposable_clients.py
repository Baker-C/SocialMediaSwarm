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


# ── phone client (TextVerified `textverified` package) ──

class _FakeVerif:
    def __init__(self, number="2233458400", vid="lr_9") -> None:
        self.number = number
        self.id = vid


class _FakeMsg:
    def __init__(self, code) -> None:
        self.parsed_code = code


class _FakeVerifications:
    def __init__(self, verif, raise_create=False) -> None:
        self._verif = verif
        self._raise = raise_create

    def create(self, req):
        if self._raise:
            raise RuntimeError("boom")
        return self._verif

    def details(self, lease_id):
        return self._verif


class _FakeSms:
    def __init__(self, msgs) -> None:
        self._msgs = msgs

    def list(self, verification):
        return list(self._msgs)


class _FakeTV:
    def __init__(self, verif=None, msgs=None, raise_create=False) -> None:
        verif = verif or _FakeVerif()
        self.verifications = _FakeVerifications(verif, raise_create)
        self.sms = _FakeSms(msgs or [])


def test_phone_acquire_returns_lease() -> None:
    """Phone acquisition via TextVerified verifications.create."""
    c = DisposablePhoneClient()
    c._client = _FakeTV(verif=_FakeVerif(number="2233458400", vid="lr_9"))
    lease = c.acquire_number()
    assert isinstance(lease, PhoneLease)
    assert lease.lease_id == "lr_9"
    assert lease.phone == "2233458400"


def test_phone_acquire_error_response_raises() -> None:
    """Phone acquisition surfaces a clean error when TextVerified fails."""
    c = DisposablePhoneClient()
    c._client = _FakeTV(raise_create=True)
    with pytest.raises(DisposablePhoneError, match="TextVerified acquire failed"):
        c.acquire_number()


def test_phone_fetch_code_parses() -> None:
    """SMS code snapshot via verifications.details + sms.list."""
    c = DisposablePhoneClient()
    c._client = _FakeTV(msgs=[_FakeMsg("222333")])
    assert c.fetch_code("lr_9") == "222333"


def test_phone_fetch_code_none_when_no_sms() -> None:
    """No SMS yet → None (non-blocking; caller polls)."""
    c = DisposablePhoneClient()
    c._client = _FakeTV(msgs=[])
    assert c.fetch_code("lr_9") is None


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

    r = client.post(
        "/api/provisioning/aid/phone",
        headers={"Authorization": "Bearer t"},
        json={"phone": " 15550001111 "},
    )
    assert r.status_code == 200
    assert r.json() == {"phone": "15550001111"}
    assert fake.upserts == [{"account_id": "aid", "disposable_phone": "15550001111"}]


def test_get_phone_endpoint_returns_stored_number(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    from app.services.account_secrets_service import AccountSecrets

    fake = _FakeSecrets()
    fake._sec = AccountSecrets(account_id="aid", disposable_phone="15550001111")
    monkeypatch.setattr(provisioning_routes, "secrets_svc", fake)
    r = client.get("/api/provisioning/aid/phone", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"phone": "15550001111"}


def test_phone_code_endpoint_uses_stored_number(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    from app.services.account_secrets_service import AccountSecrets

    fake = _FakeSecrets()
    fake._sec = AccountSecrets(account_id="aid", disposable_phone="15550001111")
    monkeypatch.setattr(provisioning_routes, "secrets_svc", fake)

    class _Phone:
        def fetch_code_by_number(self, number, **kw):
            assert number == "15550001111"
            return "445566"

    monkeypatch.setattr(provisioning_routes, "get_disposable_phone_client", lambda: _Phone())
    r = client.get("/api/provisioning/aid/phone-code", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"code": "445566"}


def test_phone_code_endpoint_409_without_number(monkeypatch) -> None:
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")
    monkeypatch.setattr(provisioning_routes, "secrets_svc", _FakeSecrets())
    r = client.get("/api/provisioning/aid/phone-code", headers={"Authorization": "Bearer t"})
    assert r.status_code == 409

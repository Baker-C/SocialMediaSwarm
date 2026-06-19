"""Backend end-to-end happy path (plan 09 §3): persona approve → start → agent
job/status/control/result → secrets round-trip decrypted, status complete, no
secret leaks via the public edit view.

No X, no agent, no network: externals are faked. Sync only (unittest.mock +
monkeypatch + TestClient). Auth is auto-bypassed by tests/conftest.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.routes import accounts as accounts_routes
from app.api.routes import persona as persona_routes
from app.api.routes import provisioning as provisioning_routes
from app.api.routes.persona_types import PersonaChatMessage, PersonaChatRequest, PersonaSpec
from app.main import app
from app.models.account import AccountDocument
from app.services import account_secrets_service, account_update_service
from app.services.account_secrets_service import AccountSecretsService

client = TestClient(app)

SPEC = {
    "handle": "cool_bot",
    "display_name": "Cool Bot",
    "bio": "I post cool things.",
    "category": "Tech",
    "personality": "Dry and witty.",
    "posting_prompt": "Post about tech.",
    "avatar_prompt": "a square robot avatar",
    "header_prompt": "a wide tech banner",
}

# Secrets the agent posts back; must round-trip decrypted and NEVER appear in /edit.
DEV_API_KEY = "devkey-AAAA1111"
DEV_API_SECRET = "devsecret-BBBB2222"
DEV_BEARER = "devbearer-CCCC3333"
PASSWORD = "hunter2-DDDD4444"


class _FakeAccountRepo:
    def __init__(self) -> None:
        self.store: dict[str, AccountDocument] = {}

    def load(self, account_id: str) -> AccountDocument | None:
        return self.store.get(account_id)

    def save(self, acc: AccountDocument) -> None:
        self.store[acc.account_id] = acc


class _FakeSecretsRepo:
    """In-memory AccountSecrets store (holds the ENCRYPTED document)."""

    def __init__(self) -> None:
        self.store: dict = {}

    def load(self, account_id: str):
        return self.store.get(account_id)

    def save(self, doc) -> None:
        self.store[doc.account_id] = doc


def _fake_oauth_status(account_id: str):
    from app.services.twitter_oauth2_service import OAuthConnectionStatus

    return OAuthConnectionStatus(connected=False)


def test_provisioning_happy_path_e2e(monkeypatch):
    acct_id = "e2e_acct"

    # ── real Fernet key so encrypt-on-write / decrypt-on-read genuinely round-trips ──
    monkeypatch.setattr(
        account_secrets_service.settings, "encryption_key", Fernet.generate_key().decode()
    )

    # ── shared fakes across the route singletons ──
    acct_repo = _FakeAccountRepo()
    secrets = AccountSecretsService(repo=_FakeSecretsRepo())

    monkeypatch.setattr(persona_routes, "repo", acct_repo)
    monkeypatch.setattr(accounts_routes, "repo", acct_repo)
    monkeypatch.setattr(provisioning_routes.svc, "repo", acct_repo)
    monkeypatch.setattr(provisioning_routes.svc, "secrets", secrets)
    monkeypatch.setattr(provisioning_routes, "secrets_svc", secrets)

    # /edit view loads OAuth status (RavenDB) — stub it out.
    fake_oauth = MagicMock()
    fake_oauth.return_value.connection_status.side_effect = _fake_oauth_status
    monkeypatch.setattr(account_update_service, "TwitterOAuth2Service", fake_oauth)

    # persona externals: deterministic images + Claude not used on approve.
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("a1", "h1"))

    # apply_account_create writes a minimal real account into the shared fake repo,
    # mirroring the production create path enough for the approve step + later /edit.
    def _fake_create(body):
        acc = AccountDocument.model_validate(
            {"account_id": body.account_id, "profile": {"twitter_handle": body.twitter_handle or ""}}
        )
        acct_repo.save(acc)
        return acc

    monkeypatch.setattr(persona_routes, "apply_account_create", _fake_create)

    # agent shared secret for the agent-facing routes
    monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "agent-tok")
    agent_headers = {"Authorization": "Bearer agent-tok"}

    # ── 1) persona chat (approve): writes account + provisioning draft + image refs ──
    r = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            account_id=acct_id,
            messages=[PersonaChatMessage(role="assistant", content="Here's a persona.")],
            proposal=PersonaSpec.model_validate(SPEC),
            approve=True,
        ).model_dump(),
    )
    assert r.status_code == 200
    types = [e["type"] for e in r.json()["events"]]
    assert "account_written" in types

    acc = acct_repo.load(acct_id)
    assert acc is not None
    assert acc.provisioning.status == "draft"
    assert acc.provisioning.display_name == "Cool Bot"
    assert acc.provisioning.images.avatar_asset_id == "a1"
    assert acc.provisioning.images.header_asset_id == "h1"

    # ── 2) start → in_progress ──
    r = client.post(f"/api/provisioning/{acct_id}/start")
    assert r.status_code == 202
    assert acct_repo.load(acct_id).provisioning.status == "in_progress"

    # ── 3) simulate the agent ──
    # pre-seed the disposable inbox so build_job doesn't lazily mint one (no network).
    secrets.upsert(acct_id, disposable_email="cool_bot-xyz@example.test")

    # job
    r = client.get(f"/api/provisioning/{acct_id}/job", headers=agent_headers)
    assert r.status_code == 200
    assert r.json()["handle"] == "cool_bot"

    # status push: awaiting_captcha
    r = client.post(
        f"/api/provisioning/{acct_id}/status",
        json={"status": "awaiting_captcha", "current_page": "captcha"},
        headers=agent_headers,
    )
    assert r.status_code == 200
    assert acct_repo.load(acct_id).provisioning.status == "awaiting_captcha"

    # frontend resolves the pause
    r = client.post(f"/api/provisioning/{acct_id}/control", json={"action": "continue"})
    assert r.status_code == 200

    # agent polls control: returns "continue" then clears
    r = client.get(f"/api/provisioning/{acct_id}/control", headers=agent_headers)
    assert r.json() == {"action": "continue"}
    r = client.get(f"/api/provisioning/{acct_id}/control", headers=agent_headers)
    assert r.json() == {"action": ""}

    # agent posts the result with dev keys
    r = client.post(
        f"/api/provisioning/{acct_id}/result",
        json={
            "x_user_id": "999",
            "dev_app_id": "app-1",
            "password": PASSWORD,
            "dev_api_key": DEV_API_KEY,
            "dev_api_secret": DEV_API_SECRET,
            "dev_bearer_token": DEV_BEARER,
        },
        headers=agent_headers,
    )
    assert r.status_code == 200

    # ── 4) assertions ──
    # secrets round-trip DECRYPTED server-side
    sec = secrets.get(acct_id)
    assert sec is not None
    assert sec.password == PASSWORD
    assert sec.dev_api_key == DEV_API_KEY
    assert sec.dev_api_secret == DEV_API_SECRET
    assert sec.dev_bearer_token == DEV_BEARER

    # status complete
    assert acct_repo.load(acct_id).provisioning.status == "complete"

    # no secret value leaks via the public edit view
    r = client.get(f"/api/accounts/{acct_id}/edit")
    assert r.status_code == 200
    body = r.text
    for secret in (PASSWORD, DEV_API_KEY, DEV_API_SECRET, DEV_BEARER):
        assert secret not in body

"""Persona-design chat API tests (doc 03).

Tests the persona state machine with a fake Claude client (no network) and the
buffered JSON fallback path (no SSE header). Covers: a chat turn emits
assistant_message + persona_preview; approve generates images, writes the
account + provisioning sub-doc, and emits account_written; defensive parse.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes import persona as persona_routes
from app.api.routes.auth import require_auth
from app.api.routes.persona_types import PersonaChatMessage, PersonaChatRequest, PersonaDraft, PersonaSpec
from app.main import app
from app.models.account import AccountDocument
from app.models.account_secrets import AccountSecretsDocument
from app.services.account_secrets_service import AccountSecrets


@pytest.fixture(autouse=True)
def _override_auth():
    """Allow tests to run without bearer tokens."""
    def mock_require_auth(authorization: str = "") -> None:
        pass

    app.dependency_overrides[require_auth] = mock_require_auth
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def _fake_claude(return_dict: dict):
    mock = MagicMock()
    mock.enabled = True
    mock.messages_json_dict.return_value = return_dict
    return mock


SPEC_DICT = {
    "handle": "cool_bot",
    "display_name": "Cool Bot",
    "bio": "I post cool things.",
    "category": "Tech",
    "personality": "Dry and witty.",
    "posting_prompt": "Post about tech.",
    "niches": ["topic one", "topic two"],
    "pipelines": ["standard", "lean"],
    "avatar_prompt": "a square robot avatar",
    "header_prompt": "a wide tech banner",
}


def test_chat_turn_emits_message_and_preview(monkeypatch):
    """A drafting turn → assistant_message + persona_preview + done."""
    monkeypatch.setattr(
        persona_routes,
        "claude",
        _fake_claude({"reply": "Here's a persona.", "spec": SPEC_DICT}),
    )

    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            account_id="acct1",
            messages=[PersonaChatMessage(role="user", content="A tech bot")],
        ).model_dump(),
    )

    assert response.status_code == 200
    events = response.json()["events"]
    assert events[0]["type"] == "assistant_message"
    assert events[0]["text"] == "Here's a persona."
    assert events[1]["type"] == "persona_preview"
    assert events[1]["spec"]["handle"] == "cool_bot"
    assert events[-1]["type"] == "done"


def test_chat_turn_no_spec(monkeypatch):
    """Pure chat turn (spec=null) → assistant_message only, no preview."""
    monkeypatch.setattr(
        persona_routes,
        "claude",
        _fake_claude({"reply": "Tell me more.", "spec": None}),
    )

    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            account_id="acct1",
            messages=[PersonaChatMessage(role="user", content="hi")],
        ).model_dump(),
    )

    events = response.json()["events"]
    assert events[0]["type"] == "assistant_message"
    assert all(e["type"] != "persona_preview" for e in events)
    assert events[-1]["type"] == "done"


def test_approve_writes_account_and_images(monkeypatch):
    """Approve → images_generating, images_ready, account_written; saves image refs,
    seeds niches from the spec, and seeds the chosen posting pipelines."""
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("a1", "h1"))

    saved: dict = {}

    fake_acc = AccountDocument.model_validate({"account_id": "cool_bot", "profile": {}})

    mock_repo = MagicMock()
    # load() is called twice: the duplicate-account check (None) then the post-create load.
    mock_repo.load.side_effect = [None, fake_acc]
    mock_repo.list_all_accounts.return_value = []  # no open slot -> parked retired

    def _save(acc):
        saved["acc"] = acc

    mock_repo.save.side_effect = _save
    monkeypatch.setattr(persona_routes, "repo", mock_repo)
    monkeypatch.setattr(persona_routes, "apply_account_create", MagicMock())
    seed = MagicMock(return_value=["standard", "lean"])
    monkeypatch.setattr(persona_routes, "seed_active_pipelines", seed)

    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            account_id="acct1",
            messages=[PersonaChatMessage(role="assistant", content="Here's a persona.")],
            proposal=PersonaSpec.model_validate(SPEC_DICT),
            approve=True,
        ).model_dump(),
    )

    assert response.status_code == 200
    events = response.json()["events"]
    types = [e["type"] for e in events]
    assert "images_generating" in types
    assert "images_ready" in types
    assert "account_written" in types
    assert events[-1]["type"] == "done"

    persona_routes.apply_account_create.assert_called_once()
    mock_repo.save.assert_called_once()
    assert saved["acc"].provisioning.images.avatar_asset_id == "a1"
    assert saved["acc"].provisioning.images.header_asset_id == "h1"
    assert saved["acc"].provisioning.display_name == "Cool Bot"
    assert saved["acc"].provisioning.status == "draft"
    assert [n.niche for n in saved["acc"].soul.niches] == ["topic one", "topic two"]
    # 1-3 chosen posting pipelines are seeded for the new account's handle.
    seed.assert_called_once_with("cool_bot", ["standard", "lean"])


def test_approve_nothing_to_approve():
    """Approve with no proposal → validation_errors + done."""
    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(account_id="acct1", approve=True).model_dump(),
    )

    events = response.json()["events"]
    assert events[0]["type"] == "validation_errors"
    assert events[-1]["type"] == "done"


def test_chat_turn_without_account_id(monkeypatch):
    """Chat works before an account id exists (entered later, not up front)."""
    monkeypatch.setattr(
        persona_routes,
        "claude",
        _fake_claude({"reply": "Here's a persona.", "spec": SPEC_DICT}),
    )

    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            messages=[PersonaChatMessage(role="user", content="A tech bot")],
        ).model_dump(),
    )

    assert response.status_code == 200
    events = response.json()["events"]
    assert events[0]["type"] == "assistant_message"
    assert events[-1]["type"] == "done"


def _slot_acct(account_id, *, souled=False, retired=False):
    return AccountDocument.model_validate({
        "account_id": account_id,
        "profile": {"status": "active", "retired": retired},
        "provisioning": {"persona_assigned": souled},
    })


def _patch_fleet(monkeypatch, accounts, phone_ids):
    """Patch persona_routes.repo + secrets so slot listing/phone checks are deterministic."""
    mock_repo = MagicMock()
    mock_repo.list_all_accounts.return_value = accounts
    monkeypatch.setattr(persona_routes, "repo", mock_repo)
    mock_secrets = MagicMock()
    mock_secrets.repo.load.side_effect = lambda aid: AccountSecretsDocument(
        account_id=aid, disposable_phone_enc=("enc" if aid in phone_ids else None))
    monkeypatch.setattr(persona_routes, "secrets", mock_secrets)
    return mock_repo, mock_secrets


def test_eligible_slots_filters_to_unsouled_active_with_phone(monkeypatch):
    accts = [
        _slot_acct("ava_b"),                    # eligible
        _slot_acct("chloe_d"),                  # eligible
        _slot_acct("no_phone"),                 # excluded: no phone
        _slot_acct("souled_x", souled=True),    # excluded: has a soul
        _slot_acct("retired_y", retired=True),  # excluded: retired
    ]
    _patch_fleet(monkeypatch, accts, phone_ids={"ava_b", "chloe_d", "souled_x", "retired_y"})
    assert [a.account_id for a in persona_routes._eligible_slots()] == ["ava_b", "chloe_d"]


def test_list_persona_slots_endpoint_masks_phone(monkeypatch):
    _patch_fleet(monkeypatch, [_slot_acct("ava_b"), _slot_acct("souled", souled=True)], phone_ids={"ava_b"})
    persona_routes.secrets.get.side_effect = lambda aid: AccountSecrets(account_id=aid, disposable_phone="5551234567")
    r = client.get("/api/persona/slots")
    assert r.status_code == 200
    slots = r.json()["slots"]
    assert [s["account_id"] for s in slots] == ["ava_b"]
    assert slots[0]["phone_last4"] == "4567"


def test_approve_uses_operator_chosen_slot(monkeypatch):
    """slot_account_id picks the slot to consume — NOT the lowest id."""
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("a1", "h1"))
    monkeypatch.setattr(persona_routes, "apply_account_create", MagicMock())
    monkeypatch.setattr(persona_routes, "seed_active_pipelines", lambda *a, **k: ["standard"])
    mock_repo, _ = _patch_fleet(monkeypatch, [_slot_acct("ava_b"), _slot_acct("chloe_d")],
                                phone_ids={"ava_b", "chloe_d"})
    # dup-check returns None, then the post-create load returns the new account.
    mock_repo.load.side_effect = [None, AccountDocument.model_validate({"account_id": "cool_bot", "profile": {}})]

    req = PersonaChatRequest(proposal=PersonaSpec.model_validate(SPEC_DICT), approve=True,
                             slot_account_id="chloe_d")  # NOT the lowest ("ava_b")
    events: list = []
    persona_routes._do_approve(req, events.append)

    assert any(e["type"] == "account_written" for e in events)
    deleted = [c.args[0] for c in mock_repo.client.delete_document.call_args_list]
    assert AccountDocument.document_id("chloe_d") in deleted     # consumed the CHOSEN slot
    assert AccountDocument.document_id("ava_b") not in deleted   # left the lowest-id slot alone


def test_approve_rejects_unknown_slot(monkeypatch):
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("a1", "h1"))
    monkeypatch.setattr(persona_routes, "apply_account_create", MagicMock())
    mock_repo, _ = _patch_fleet(monkeypatch, [_slot_acct("ava_b")], phone_ids={"ava_b"})
    mock_repo.load.return_value = None  # handle not taken

    req = PersonaChatRequest(proposal=PersonaSpec.model_validate(SPEC_DICT), approve=True,
                             slot_account_id="does_not_exist")
    events: list = []
    persona_routes._do_approve(req, events.append)

    assert events[0]["type"] == "validation_errors"
    persona_routes.apply_account_create.assert_not_called()  # bailed before any write/image work


def test_approve_without_niche_errors():
    """Approve a spec missing niches → validation_errors, before any account is written
    (guards against blank-souled accounts; the guard runs before any DB/image work)."""
    spec = {**SPEC_DICT, "niches": []}
    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(
            proposal=PersonaSpec.model_validate(spec),
            approve=True,
        ).model_dump(),
    )

    events = response.json()["events"]
    assert events[0]["type"] == "validation_errors"
    assert events[-1]["type"] == "done"


def test_regenerate_images(monkeypatch):
    """Both prompts → both asset ids returned."""
    monkeypatch.setattr(
        persona_routes,
        "generate_persona_image",
        lambda kind, prompt: "av" if kind == "avatar" else "hd",
    )

    response = client.post(
        "/api/persona/regenerate-images",
        json={"avatar_prompt": "x", "header_prompt": "y"},
    )

    assert response.status_code == 200
    assert response.json() == {"avatar_asset_id": "av", "header_asset_id": "hd"}


def test_regenerate_images_avatar_only(monkeypatch):
    """Only avatar_prompt → response has only avatar_asset_id."""
    monkeypatch.setattr(
        persona_routes,
        "generate_persona_image",
        lambda kind, prompt: "av" if kind == "avatar" else "hd",
    )

    response = client.post(
        "/api/persona/regenerate-images",
        json={"avatar_prompt": "x"},
    )

    assert response.status_code == 200
    assert response.json() == {"avatar_asset_id": "av"}


def test_regenerate_images_header_only(monkeypatch):
    """Only header_prompt → response has only header_asset_id."""
    monkeypatch.setattr(
        persona_routes,
        "generate_persona_image",
        lambda kind, prompt: "av" if kind == "avatar" else "hd",
    )

    response = client.post(
        "/api/persona/regenerate-images",
        json={"header_prompt": "y"},
    )

    assert response.status_code == 200
    assert response.json() == {"header_asset_id": "hd"}


def test_persona_draft_defensive_parse():
    """PersonaDraft.model_validate({}) falls back without raising."""
    draft = PersonaDraft.model_validate({})
    assert draft.reply == ""
    assert draft.spec is None

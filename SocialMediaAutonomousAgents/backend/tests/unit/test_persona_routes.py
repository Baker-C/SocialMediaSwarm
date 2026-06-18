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
    """Approve → images_generating, images_ready, account_written; saves image refs."""
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("a1", "h1"))

    saved: dict = {}

    fake_acc = AccountDocument.model_validate({"account_id": "acct1", "profile": {}})

    mock_repo = MagicMock()
    mock_repo.load.return_value = fake_acc

    def _save(acc):
        saved["acc"] = acc

    mock_repo.save.side_effect = _save
    monkeypatch.setattr(persona_routes, "repo", mock_repo)
    monkeypatch.setattr(persona_routes, "apply_account_create", MagicMock())

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


def test_approve_nothing_to_approve():
    """Approve with no proposal → validation_errors + done."""
    response = client.post(
        "/api/persona/chat",
        json=PersonaChatRequest(account_id="acct1", approve=True).model_dump(),
    )

    events = response.json()["events"]
    assert events[0]["type"] == "validation_errors"
    assert events[-1]["type"] == "done"


def test_regenerate_images(monkeypatch):
    """Regenerate endpoint returns fresh asset ids."""
    monkeypatch.setattr(persona_routes, "generate_persona_images", lambda a, h: ("av", "hd"))

    response = client.post(
        "/api/persona/regenerate-images",
        json={"avatar_prompt": "x", "header_prompt": "y"},
    )

    assert response.status_code == 200
    assert response.json() == {"avatar_asset_id": "av", "header_asset_id": "hd"}


def test_persona_draft_defensive_parse():
    """PersonaDraft.model_validate({}) falls back without raising."""
    draft = PersonaDraft.model_validate({})
    assert draft.reply == ""
    assert draft.spec is None

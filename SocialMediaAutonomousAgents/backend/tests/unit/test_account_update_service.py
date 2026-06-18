from unittest.mock import MagicMock

import pytest

from app.models.account import AccountDocument
from app.services.account_update_service import AccountUpdateBody, account_edit_view, apply_account_update


def _doc(**kwargs: object) -> AccountDocument:
    base: dict = {
        "account_id": "aid",
        "category": "category",
        "twitter_handle": "@h",
        "status": "active",
    }
    base.update(kwargs)
    return AccountDocument.model_validate(base)


def test_account_edit_view_has_no_encrypted_fields() -> None:
    acc = _doc()
    oauth = MagicMock()
    oauth.connection_status.return_value = MagicMock(connected=False, expires_at=None)
    view = account_edit_view(acc, oauth=oauth)
    assert view["account_id"] == "aid"
    assert not any(k.endswith("_enc") for k in view)
    assert view["credential_mode"] == "none"
    assert "personality" in view
    assert "posting_prompt" in view
    assert "system_prompt" not in view and "negative_semantics" not in view
    assert isinstance(view["contrast_patterns"], list) and len(view["contrast_patterns"]) >= 1
    assert isinstance(view["punctuation_rules"], list) and len(view["punctuation_rules"]) >= 1


def test_apply_updates_category() -> None:
    acc = _doc(category="old")
    saved: list[AccountDocument] = []

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            return acc if account_id == "aid" else None

        def save(self, a: AccountDocument) -> None:
            saved.append(a)

    body = AccountUpdateBody(category="brand-new")
    out = apply_account_update("aid", body, repo=R())
    assert out.category == "brand-new"
    assert len(saved) == 1

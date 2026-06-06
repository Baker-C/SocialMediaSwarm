from unittest.mock import MagicMock

import pytest

from app.models.account import AccountDocument
from app.services.account_update_service import AccountUpdateBody, account_edit_view, apply_account_update


def _doc(**kwargs: object) -> AccountDocument:
    base: dict = {
        "account_id": "aid",
        "niche": "niche",
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
    assert isinstance(view["negative_semantics"], list)
    assert len(view["negative_semantics"]) >= 1


def test_apply_updates_niche() -> None:
    acc = _doc(niche="old")
    saved: list[AccountDocument] = []

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            return acc if account_id == "aid" else None

        def save(self, a: AccountDocument) -> None:
            saved.append(a)

    body = AccountUpdateBody(niche="brand-new")
    out = apply_account_update("aid", body, repo=R())
    assert out.niche == "brand-new"
    assert len(saved) == 1

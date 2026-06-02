from cryptography.fernet import Fernet
from unittest.mock import MagicMock

import pytest

from app.models.account import AccountDocument
from app.services import account_update_service as aus
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
    view = account_edit_view(acc)
    assert view["account_id"] == "aid"
    assert not any(k.endswith("_enc") for k in view)
    assert "personality" in view
    assert isinstance(view["negative_semantics"], list)
    assert len(view["negative_semantics"]) >= 1


def test_apply_updates_niche_without_touching_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(aus.settings, "encryption_key", key)
    acc = _doc(niche="old", twitter_oauth2_access_token_enc="blob")
    saved: list[AccountDocument] = []

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            return acc if account_id == "aid" else None

        def save(self, a: AccountDocument) -> None:
            saved.append(a)

    r = R()
    body = AccountUpdateBody(niche="brand-new")
    out = apply_account_update("aid", body, repo=r)
    assert out.niche == "brand-new"
    assert len(saved) == 1
    assert saved[0].twitter_oauth2_access_token_enc == "blob"


def test_apply_sets_oauth2_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(aus.settings, "encryption_key", key)
    acc = _doc()
    saved: list[AccountDocument] = []

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            return acc if account_id == "aid" else None

        def save(self, a: AccountDocument) -> None:
            saved.append(a)

    body = AccountUpdateBody(
        twitter_oauth2_access_token="o2",
        twitter_oauth2_refresh_token="r2",
    )
    out = apply_account_update("aid", body, repo=R())
    assert out.twitter_oauth2_access_token_enc
    assert out.twitter_oauth2_refresh_token_enc
    assert len(saved) == 1

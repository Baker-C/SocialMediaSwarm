from cryptography.fernet import Fernet

import pytest

from app.models.account_secrets import AccountSecretsDocument
from app.services import account_secrets_service as mod
from app.services.account_secrets_service import AccountSecretsService


class R:
    """Inline fake repo backed by a dict keyed on account_id."""

    def __init__(self) -> None:
        self.store: dict[str, AccountSecretsDocument] = {}

    def load(self, account_id: str) -> AccountSecretsDocument | None:
        return self.store.get(account_id)

    def save(self, doc: AccountSecretsDocument) -> None:
        self.store[doc.account_id] = doc


def _set_key(monkeypatch) -> None:
    monkeypatch.setattr(mod.settings, "encryption_key", Fernet.generate_key().decode())


def test_round_trip_encrypts_and_decrypts(monkeypatch) -> None:
    _set_key(monkeypatch)
    repo = R()
    svc = AccountSecretsService(repo=repo)

    svc.upsert("aid", dev_api_key="k")

    stored = repo.store["aid"]
    assert stored.dev_api_key_enc is not None
    assert stored.dev_api_key_enc != "k"  # ciphertext != plaintext

    out = svc.get("aid")
    assert out is not None
    assert out.dev_api_key == "k"


def test_partial_upsert_preserves_prior_fields(monkeypatch) -> None:
    _set_key(monkeypatch)
    repo = R()
    svc = AccountSecretsService(repo=repo)

    svc.upsert("aid", password="pw")
    svc.upsert("aid", dev_api_key="k", dev_api_secret="s")

    out = svc.get("aid")
    assert out is not None
    assert out.password == "pw"
    assert out.dev_api_key == "k"
    assert out.dev_api_secret == "s"


def test_missing_encryption_key_raises(monkeypatch) -> None:
    monkeypatch.setattr(mod.settings, "encryption_key", "")
    svc = AccountSecretsService(repo=R())

    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        svc.upsert("aid", dev_api_key="k")


def test_get_missing_returns_none(monkeypatch) -> None:
    _set_key(monkeypatch)
    svc = AccountSecretsService(repo=R())
    assert svc.get("nope") is None

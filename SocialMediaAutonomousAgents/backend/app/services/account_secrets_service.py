"""Encrypt-on-write / decrypt-on-read service for per-account secrets."""

from __future__ import annotations

from pydantic import BaseModel

from app.core.config import settings
from app.models.account_secrets import AccountSecretsDocument
from app.services.account_secrets_repository import AccountSecretsRepository
from app.utils.encryption import decrypt_value, encrypt_value, fernet_from_key


def _fernet():
    key = (settings.encryption_key or "").strip()
    return fernet_from_key(key) if key else None


def _enc(value: str | None) -> str | None:
    if value is None:
        return None
    f = _fernet()
    if f is None:
        raise ValueError("ENCRYPTION_KEY is missing; cannot store account secrets")
    return encrypt_value(f, value)


def _dec(token: str | None) -> str | None:
    if token is None:
        return None
    f = _fernet()
    if f is None:
        raise ValueError("ENCRYPTION_KEY is missing; cannot read account secrets")
    return decrypt_value(f, token)


# Plaintext DTO returned to backend callers only (never serialized to a response model)
class AccountSecrets(BaseModel):
    account_id: str
    password: str | None = None
    disposable_email: str | None = None
    disposable_phone: str | None = None
    session_cookies: str | None = None
    dev_api_key: str | None = None
    dev_api_secret: str | None = None
    dev_bearer_token: str | None = None


class AccountSecretsService:
    def __init__(self, repo: AccountSecretsRepository | None = None) -> None:
        self.repo = repo or AccountSecretsRepository()

    def get(self, account_id: str) -> AccountSecrets | None:
        doc = self.repo.load(account_id)
        if doc is None:
            return None
        return AccountSecrets(
            account_id=account_id,
            password=_dec(doc.password_enc),
            disposable_email=_dec(doc.disposable_email_enc),
            disposable_phone=_dec(doc.disposable_phone_enc),
            session_cookies=_dec(doc.session_cookies_enc),
            dev_api_key=_dec(doc.dev_api_key_enc),
            dev_api_secret=_dec(doc.dev_api_secret_enc),
            dev_bearer_token=_dec(doc.dev_bearer_token_enc),
        )

    def upsert(self, account_id: str, **fields: str | None) -> None:
        """Partial update: only provided plaintext fields are (re)encrypted; others preserved."""
        doc = self.repo.load(account_id) or AccountSecretsDocument(account_id=account_id)
        mapping = {
            "password": "password_enc",
            "disposable_email": "disposable_email_enc",
            "disposable_phone": "disposable_phone_enc",
            "session_cookies": "session_cookies_enc",
            "dev_api_key": "dev_api_key_enc",
            "dev_api_secret": "dev_api_secret_enc",
            "dev_bearer_token": "dev_bearer_token_enc",
        }
        for plain_key, enc_key in mapping.items():
            if plain_key in fields:
                setattr(doc, enc_key, _enc(fields[plain_key]))
        doc.updated_at = fields.get("updated_at") or doc.updated_at
        self.repo.save(doc)

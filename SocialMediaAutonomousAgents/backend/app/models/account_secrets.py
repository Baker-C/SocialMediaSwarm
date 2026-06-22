"""Per-account secrets stored separately from account profile documents."""

from __future__ import annotations

from pydantic import BaseModel


class AccountSecretsDocument(BaseModel):
    """Per-account encrypted secrets in RavenDB collection ``AccountSecrets``."""

    account_id: str
    # X consumer account
    password_enc: str | None = None
    disposable_email_enc: str | None = None
    disposable_phone_enc: str | None = None
    disposable_phone_lease_enc: str | None = None  # TextVerified verification id (for SMS polling)
    session_cookies_enc: str | None = None  # JSON blob of Playwright storage_state, encrypted
    # X developer (pay-per-use)
    dev_api_key_enc: str | None = None
    dev_api_secret_enc: str | None = None
    dev_bearer_token_enc: str | None = None
    updated_at: str | None = None

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"account-secrets/{account_id}"

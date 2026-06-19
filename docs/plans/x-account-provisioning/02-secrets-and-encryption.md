# 02 — Secrets & Encryption: `AccountSecrets`

**Touches:** `backend/app/models/account_secrets.py` (new), `backend/app/services/account_secrets_repository.py` (new), `backend/app/services/account_secrets_service.py` (new)

Per-account secrets — X login password, dev API key/secret/bearer, the authenticated browser
session cookies, and the disposable email/phone used — are stored in a **separate encrypted
collection**, mirroring `OAuthTokens`. They are **never** placed on `AccountDocument`.

This is the canonical encrypted-collection pattern from `oauth_token.py` +
`oauth_token_repository.py` + `twitter_oauth2_service.py` (`_fernet/_encrypt/_decrypt`, lines 53-96).

## 1. Model — `account_secrets.py`

`*_enc` suffix = ciphertext (the house convention from `OAuthTokenDocument`).

```python
from __future__ import annotations
from pydantic import BaseModel

class AccountSecretsDocument(BaseModel):
    account_id: str
    # X consumer account
    password_enc: str | None = None
    disposable_email_enc: str | None = None
    disposable_phone_enc: str | None = None
    session_cookies_enc: str | None = None   # JSON blob of Playwright storage_state, encrypted
    # X developer (pay-per-use)
    dev_api_key_enc: str | None = None
    dev_api_secret_enc: str | None = None
    dev_bearer_token_enc: str | None = None
    updated_at: str | None = None

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"account-secrets/{account_id}"
```

Collection: `AccountSecrets`. Document id: `account-secrets/{account_id}`.

## 2. Repository — `account_secrets_repository.py`

Copy `OAuthTokenRepository` verbatim in shape (lazy `client` property, `_strip_metadata`,
`model_validate` on read, `model_dump(exclude_none=True)` + explicit `collection=` on write):

```python
def _strip_metadata(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not str(k).startswith("@")}

class AccountSecretsRepository:
    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        return self._client or get_ravendb_client()

    def load(self, account_id: str) -> AccountSecretsDocument | None:
        raw = self.client.get_document(AccountSecretsDocument.document_id(account_id))
        return AccountSecretsDocument.model_validate(_strip_metadata(raw)) if raw else None

    def save(self, doc: AccountSecretsDocument) -> None:
        self.client.put_document(
            AccountSecretsDocument.document_id(doc.account_id),
            doc.model_dump(exclude_none=True),
            collection="AccountSecrets",
        )
```

No `list_*` is needed (secrets are fetched by id only). If one is ever added, use the
`try/except RavenDBHttpError → from @all where startsWith(id(),'account-secrets/')` fallback.

## 3. Service — `account_secrets_service.py`

Owns encrypt-on-write / decrypt-on-read so callers never touch Fernet. Mirror
`TwitterOAuth2Service._fernet/_encrypt/_decrypt`.

```python
from app.core.config import settings
from app.utils.encryption import fernet_from_key, encrypt_value, decrypt_value

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
        doc.updated_at = fields.get("updated_at") or doc.updated_at  # caller passes ISO; see note
        self.repo.save(doc)
```

> **Timestamp note:** the codebase stamps ISO strings at the call site (no `Date.now()` in models).
> The provisioning service passes `updated_at=` when it calls `upsert`.

## 4. Why a single `ENCRYPTION_KEY`, not per-account KDF

Earlier planning floated per-account derived keys. **Decision: reuse the existing single
`ENCRYPTION_KEY`** (as `OAuthTokens` already does). Rationale: it's the established pattern, the
threat model here (local/throwaway operation) doesn't justify the added key-management complexity,
and consistency with `oauth_token` keeps one encryption story in the codebase. A per-account KDF can
be layered later by changing only `_fernet()` to derive `fernet_from_key(kdf(master, account_id))` —
noted as a future option, not built now.

## 5. The card stays in `.env`

Per the user's decision, the pay-per-use card is **not** an `AccountSecrets` field — it's process-wide
config read by the agent's billing handler (see `07`/`06`). One operator card for all accounts.

## 6. Tests (`tests/unit/test_account_secrets_service.py`)

Follow the `test_twitter_oauth2_service.py` style (`monkeypatch.setattr(mod.settings, ...)` + inject a
fake repo):
- Set `settings.encryption_key` to a generated Fernet key; `upsert(account_id, dev_api_key="k")`
  then `get(...)` returns `dev_api_key == "k"` and the stored doc's `dev_api_key_enc != "k"`.
- Partial `upsert` preserves previously-stored fields (write password, then write dev keys; both readable).
- With `settings.encryption_key = ""`, `upsert`/`get` raise `ValueError` mentioning `ENCRYPTION_KEY`.
- Fake repo is an inline `class R:` with `load`/`save` over a dict (mirrors `test_account_update_service.py:39`).

## Done when
- Model + repo + service exist; collection `AccountSecrets`, ids `account-secrets/{id}`.
- Encrypt-on-write / decrypt-on-read verified by round-trip test; ciphertext ≠ plaintext.
- Missing-key path raises a clear `ValueError`.
- No secret field is reachable from any response/view (reviewer check; grep `AccountSecrets` usage).

"""Create or update account documents in RavenDB — invoked from CLI only (not HTTP)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.utils.encryption import encrypt_value, fernet_from_key

if TYPE_CHECKING:
    from app.models.account import AccountDocument

logger = logging.getLogger(__name__)


class CreateAccountJobError(ValueError):
    """Invalid arguments or missing configuration for account provisioning."""


def run_create_account_job(
    *,
    account_id: str,
    niche: str | None = None,
    twitter_handle: str = "",
    twitter_api_key: str | None = None,
    twitter_api_secret: str | None = None,
    twitter_access_token: str | None = None,
    twitter_access_token_secret: str | None = None,
    twitter_oauth2_access_token: str | None = None,
    twitter_oauth2_refresh_token: str | None = None,
    repo: AccountRepository | None = None,
) -> AccountDocument:
    """
    Upsert one account with encrypted X credentials.

    **OAuth 2.0 user context** — when ``twitter_oauth2_access_token`` is non-empty:
    encrypts access (and optional refresh) token, clears OAuth1 credential fields.

    **OAuth 1.0a** — otherwise requires all four OAuth1 plaintext fields and clears
    OAuth2 token fields on the document.
    """
    aid = (account_id or "").strip()
    if not aid:
        raise CreateAccountJobError("account_id is required")

    if not settings.encryption_key or not settings.encryption_key.strip():
        raise CreateAccountJobError(
            "Set ENCRYPTION_KEY in backend/.env (Fernet key, urlsafe base64)."
        )

    f = fernet_from_key(settings.encryption_key.strip())
    r = repo or AccountRepository()

    oauth2_access = (twitter_oauth2_access_token or "").strip()
    if oauth2_access:
        enc_oauth2: dict[str, str | None] = {
            "twitter_oauth2_access_token_enc": encrypt_value(f, oauth2_access),
        }
        ref = (twitter_oauth2_refresh_token or "").strip()
        if ref:
            enc_oauth2["twitter_oauth2_refresh_token_enc"] = encrypt_value(f, ref)
        acc = r.upsert_credentials(
            aid,
            niche=niche,
            twitter_handle=twitter_handle or None,
            status="active",
            twitter_api_key_enc=None,
            twitter_api_secret_enc=None,
            twitter_access_token_enc=None,
            twitter_access_token_secret_enc=None,
            **enc_oauth2,
            clear_twitter_oauth1=True,
        )
        logger.info("create_account_job: upserted account_id=%s (OAuth2 user token)", acc.account_id)
        return acc

    missing = [
        n
        for n, v in [
            ("twitter_api_key", twitter_api_key),
            ("twitter_api_secret", twitter_api_secret),
            ("twitter_access_token", twitter_access_token),
            ("twitter_access_token_secret", twitter_access_token_secret),
        ]
        if not v
    ]
    if missing:
        raise CreateAccountJobError(
            "Account requires OAuth1: " + ", ".join(missing)
            + " — or pass twitter_oauth2_access_token for OAuth 2.0 user context."
        )

    enc = {
        "twitter_api_key_enc": encrypt_value(f, twitter_api_key or ""),
        "twitter_api_secret_enc": encrypt_value(f, twitter_api_secret or ""),
        "twitter_access_token_enc": encrypt_value(f, twitter_access_token or ""),
        "twitter_access_token_secret_enc": encrypt_value(f, twitter_access_token_secret or ""),
    }
    acc = r.upsert_credentials(
        aid,
        niche=niche,
        twitter_handle=twitter_handle or None,
        status="active",
        **enc,
        clear_twitter_oauth2=True,
    )
    logger.info("create_account_job: upserted account_id=%s (OAuth1)", acc.account_id)
    return acc

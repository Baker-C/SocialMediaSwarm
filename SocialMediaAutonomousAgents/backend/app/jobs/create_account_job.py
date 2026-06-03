"""Create account documents in RavenDB — invoked from HTTP POST, CLI, or scripts."""

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
    twitter_oauth2_access_token: str | None = None,
    twitter_oauth2_refresh_token: str | None = None,
    repo: AccountRepository | None = None,
) -> AccountDocument:
    """
    Upsert one account with encrypted OAuth2 X credentials.
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
    if not oauth2_access:
        raise CreateAccountJobError("twitter_oauth2_access_token is required")
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
        **enc_oauth2,
    )
    logger.info("create_account_job: upserted account_id=%s (OAuth2 user token)", acc.account_id)
    return acc

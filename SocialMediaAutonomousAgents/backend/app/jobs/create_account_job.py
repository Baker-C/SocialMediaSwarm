"""Create account documents in RavenDB — invoked from HTTP POST, CLI, or scripts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.account_repository import AccountRepository

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
    repo: AccountRepository | None = None,
) -> AccountDocument:
    """Upsert one account profile. OAuth tokens are connected separately via /api/oauth/x/authorize."""
    aid = (account_id or "").strip()
    if not aid:
        raise CreateAccountJobError("account_id is required")

    r = repo or AccountRepository()
    acc = r.upsert_profile(
        aid,
        niche=niche,
        twitter_handle=twitter_handle or None,
        status="active",
    )
    logger.info("create_account_job: upserted account_id=%s (connect OAuth via /api/oauth/x/authorize)", acc.account_id)
    return acc

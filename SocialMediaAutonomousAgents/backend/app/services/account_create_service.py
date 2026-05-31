"""HTTP account creation — wraps ``run_create_account_job`` and optional profile fields."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.account_update_service import AccountUpdateBody, apply_account_update


class AccountCreateBody(BaseModel):
    """POST body for provisioning a new account (credentials required)."""

    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(min_length=1, max_length=500)
    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default="active", max_length=64)
    system_prompt: str | None = Field(default=None, max_length=32000)
    personality: str | None = Field(default=None, max_length=16000)
    negative_semantics: list[str] | None = None
    buffer_organization_id: str | None = Field(default=None, max_length=500)
    buffer_channel_id: str | None = Field(default=None, max_length=500)
    twitter_api_key: str | None = None
    twitter_api_secret: str | None = None
    twitter_access_token: str | None = None
    twitter_access_token_secret: str | None = None
    twitter_oauth2_access_token: str | None = None
    twitter_oauth2_refresh_token: str | None = None


class AccountAlreadyExistsError(ValueError):
    """Raised when ``account_id`` is already stored."""


def apply_account_create(body: AccountCreateBody, repo: AccountRepository | None = None) -> AccountDocument:
    aid = (body.account_id or "").strip()
    if not aid:
        raise ValueError("account_id is required")

    r = repo or AccountRepository()
    if r.load(aid) is not None:
        raise AccountAlreadyExistsError(f"Account already exists: {aid}")

    try:
        acc = run_create_account_job(
            account_id=aid,
            niche=body.niche,
            twitter_handle=body.twitter_handle or "",
            twitter_api_key=body.twitter_api_key,
            twitter_api_secret=body.twitter_api_secret,
            twitter_access_token=body.twitter_access_token,
            twitter_access_token_secret=body.twitter_access_token_secret,
            twitter_oauth2_access_token=body.twitter_oauth2_access_token,
            twitter_oauth2_refresh_token=body.twitter_oauth2_refresh_token,
            repo=r,
        )
    except CreateAccountJobError as exc:
        raise ValueError(str(exc)) from exc

    profile_fields = (
        body.status,
        body.system_prompt,
        body.personality,
        body.negative_semantics,
        body.buffer_organization_id,
        body.buffer_channel_id,
    )
    if any(v is not None for v in profile_fields):
        update = AccountUpdateBody(
            status=body.status,
            system_prompt=body.system_prompt,
            personality=body.personality,
            negative_semantics=body.negative_semantics,
            buffer_organization_id=body.buffer_organization_id,
            buffer_channel_id=body.buffer_channel_id,
        )
        acc = apply_account_update(aid, update, repo=r)

    return acc

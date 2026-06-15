"""HTTP account creation — wraps ``run_create_account_job`` and optional profile fields."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.account_update_service import AccountUpdateBody, apply_account_update


class AccountCreateBody(BaseModel):
    """POST body for provisioning a new account profile (OAuth connected separately)."""

    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(min_length=1, max_length=500)
    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default="active", max_length=64)
    posting_prompt: str | None = Field(default=None, max_length=32000)   # was system_prompt
    personality: str | None = Field(default=None, max_length=16000)
    contrast_patterns: list | None = None                                # was negative_semantics
    punctuation_rules: list | None = None                                # NEW


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
            repo=r,
        )
    except CreateAccountJobError as exc:
        raise ValueError(str(exc)) from exc

    profile_fields = (
        body.status,
        body.posting_prompt,
        body.personality,
        body.contrast_patterns,
        body.punctuation_rules,
    )
    if any(v is not None for v in profile_fields):
        update = AccountUpdateBody(
            status=body.status,
            posting_prompt=body.posting_prompt,
            personality=body.personality,
            contrast_patterns=body.contrast_patterns,
            punctuation_rules=body.punctuation_rules,
        )
        acc = apply_account_update(aid, update, repo=r)

    return acc

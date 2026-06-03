"""Merge HTTP account edit payloads into ``AccountDocument`` rows (no secrets in GET)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.account import AccountDocument, default_negative_semantics, default_system_prompt
from app.services.account_repository import AccountRepository
from app.utils.encryption import encrypt_value, fernet_from_key


class AccountUpdateBody(BaseModel):
    """PATCH body: ``None`` / omitted fields leave existing document values unchanged."""

    model_config = ConfigDict(extra="ignore")

    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)
    system_prompt: str | None = Field(default=None, max_length=32000)
    personality: str | None = Field(default=None, max_length=16000)
    negative_semantics: list[str] | None = None
    followers: int | None = Field(default=None, ge=0)
    posts_total: int | None = Field(default=None, ge=0)
    twitter_oauth2_access_token: str | None = None
    twitter_oauth2_refresh_token: str | None = None


def _has_oauth2_on_doc(acc: AccountDocument) -> bool:
    return bool((acc.credentials.oauth2_access_token_enc or "").strip())


def account_edit_view(acc: AccountDocument) -> dict:
    """Safe JSON for the dashboard edit form (no ciphertext or plaintext secrets)."""
    niche = acc.niche or ""
    mode = "oauth2" if _has_oauth2_on_doc(acc) else "none"
    return {
        "account_id": acc.account_id,
        "niche": niche,
        "twitter_handle": acc.twitter_handle or "",
        "status": acc.status or "active",
        "system_prompt": (acc.system_prompt or "").strip() or default_system_prompt(niche),
        "personality": (acc.personality or "").strip(),
        "negative_semantics": list(acc.negative_semantics or default_negative_semantics()),
        "followers": acc.followers,
        "posts_total": acc.posts_total,
        "registered_at": acc.registered_at,
        "last_interval_slot": acc.last_interval_slot,
        "last_post_id": acc.last_post_id,
        "credential_mode": mode,
    }


def apply_account_update(account_id: str, body: AccountUpdateBody, repo: AccountRepository | None = None) -> AccountDocument:
    aid = (account_id or "").strip()
    if not aid:
        raise ValueError("account_id is required")

    r = repo or AccountRepository()
    existing = r.load(aid)
    if existing is None:
        raise LookupError("Account not found")

    if not settings.encryption_key or not settings.encryption_key.strip():
        raise ValueError("ENCRYPTION_KEY is missing or empty; cannot encrypt X credentials")

    f = fernet_from_key(settings.encryption_key.strip())
    data = existing.model_dump()
    profile = data.setdefault("profile", {})
    voice = data.setdefault("voice", {})
    credentials = data.setdefault("credentials", {})

    if body.niche is not None:
        niche = body.niche.strip() or existing.niche or aid
        profile["niche"] = niche
    niche = profile.get("niche") or existing.niche or aid

    if body.twitter_handle is not None:
        profile["twitter_handle"] = body.twitter_handle.strip()

    if body.status is not None:
        profile["status"] = (body.status or "active").strip() or "active"

    if body.system_prompt is not None:
        sp = body.system_prompt.strip()
        voice["system_prompt"] = sp if sp else default_system_prompt(niche)

    if body.personality is not None:
        voice["personality"] = body.personality.strip()

    if body.negative_semantics is not None:
        cleaned = [s.strip() for s in body.negative_semantics if s and str(s).strip()]
        voice["negative_semantics"] = cleaned if cleaned else default_negative_semantics()

    if body.followers is not None:
        profile["followers"] = body.followers

    if body.posts_total is not None:
        profile["posts_total"] = body.posts_total

    o2 = ((body.twitter_oauth2_access_token or "") if body.twitter_oauth2_access_token is not None else "").strip()

    if o2:
        credentials["oauth2_access_token_enc"] = encrypt_value(f, o2)
        ref = (
            (body.twitter_oauth2_refresh_token or "").strip()
            if body.twitter_oauth2_refresh_token is not None
            else ""
        )
        if ref:
            credentials["oauth2_refresh_token_enc"] = encrypt_value(f, ref)
        else:
            credentials["oauth2_refresh_token_enc"] = None

    acc = AccountDocument.model_validate(data)
    r.save(acc)
    return acc

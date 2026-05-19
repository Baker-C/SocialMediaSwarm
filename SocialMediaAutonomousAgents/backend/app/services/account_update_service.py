"""Merge HTTP account edit payloads into ``AccountDocument`` rows (no secrets in GET)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.account import AccountDocument, default_system_prompt
from app.services.account_repository import AccountRepository
from app.utils.encryption import encrypt_value, fernet_from_key


class AccountUpdateBody(BaseModel):
    """PATCH body: ``None`` / omitted fields leave existing document values unchanged."""

    model_config = ConfigDict(extra="ignore")

    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)
    system_prompt: str | None = Field(default=None, max_length=32000)
    buffer_organization_id: str | None = Field(default=None, max_length=500)
    buffer_channel_id: str | None = Field(default=None, max_length=500)
    followers: int | None = Field(default=None, ge=0)
    posts_total: int | None = Field(default=None, ge=0)
    twitter_api_key: str | None = None
    twitter_api_secret: str | None = None
    twitter_access_token: str | None = None
    twitter_access_token_secret: str | None = None
    twitter_oauth2_access_token: str | None = None
    twitter_oauth2_refresh_token: str | None = None


def _has_oauth1_on_doc(acc: AccountDocument) -> bool:
    return bool(
        acc.twitter_api_key_enc
        and acc.twitter_api_secret_enc
        and acc.twitter_access_token_enc
        and acc.twitter_access_token_secret_enc
    )


def _has_oauth2_on_doc(acc: AccountDocument) -> bool:
    return bool((acc.twitter_oauth2_access_token_enc or "").strip())


def account_edit_view(acc: AccountDocument) -> dict:
    """Safe JSON for the dashboard edit form (no ciphertext or plaintext secrets)."""
    niche = acc.niche or ""
    mode = "oauth2" if _has_oauth2_on_doc(acc) else ("oauth1" if _has_oauth1_on_doc(acc) else "none")
    return {
        "account_id": acc.account_id,
        "niche": niche,
        "twitter_handle": acc.twitter_handle or "",
        "status": acc.status or "active",
        "system_prompt": (acc.system_prompt or "").strip() or default_system_prompt(niche),
        "buffer_organization_id": acc.buffer_organization_id or "",
        "buffer_channel_id": acc.buffer_channel_id or "",
        "followers": acc.followers,
        "posts_total": acc.posts_total,
        "registered_at": acc.registered_at,
        "last_post_slot": acc.last_post_slot,
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

    if body.niche is not None:
        niche = body.niche.strip() or existing.niche or aid
        data["niche"] = niche
    niche = data.get("niche") or existing.niche or aid

    if body.twitter_handle is not None:
        data["twitter_handle"] = body.twitter_handle.strip()

    if body.status is not None:
        data["status"] = (body.status or "active").strip() or "active"

    if body.system_prompt is not None:
        sp = body.system_prompt.strip()
        data["system_prompt"] = sp if sp else default_system_prompt(niche)

    if body.followers is not None:
        data["followers"] = body.followers

    if body.posts_total is not None:
        data["posts_total"] = body.posts_total

    if body.buffer_organization_id is not None:
        bo = body.buffer_organization_id.strip()
        data["buffer_organization_id"] = bo or None
    if body.buffer_channel_id is not None:
        bc = body.buffer_channel_id.strip()
        data["buffer_channel_id"] = bc or None

    o2 = ((body.twitter_oauth2_access_token or "") if body.twitter_oauth2_access_token is not None else "").strip()
    k1 = ((body.twitter_api_key or "") if body.twitter_api_key is not None else "").strip()
    s1 = ((body.twitter_api_secret or "") if body.twitter_api_secret is not None else "").strip()
    t1 = ((body.twitter_access_token or "") if body.twitter_access_token is not None else "").strip()
    ts1 = ((body.twitter_access_token_secret or "") if body.twitter_access_token_secret is not None else "").strip()
    oauth1_any = bool(k1 or s1 or t1 or ts1)

    if o2 and oauth1_any:
        raise ValueError("Provide either OAuth 2.0 user access token or OAuth 1.0a four keys, not both")

    if o2:
        enc_o2: dict[str, str | None] = {
            "twitter_oauth2_access_token_enc": encrypt_value(f, o2),
        }
        ref = (
            (body.twitter_oauth2_refresh_token or "").strip()
            if body.twitter_oauth2_refresh_token is not None
            else ""
        )
        if ref:
            enc_o2["twitter_oauth2_refresh_token_enc"] = encrypt_value(f, ref)
        else:
            enc_o2["twitter_oauth2_refresh_token_enc"] = None
        data["twitter_oauth2_access_token_enc"] = enc_o2["twitter_oauth2_access_token_enc"]
        data["twitter_oauth2_refresh_token_enc"] = enc_o2["twitter_oauth2_refresh_token_enc"]
        data["twitter_api_key_enc"] = None
        data["twitter_api_secret_enc"] = None
        data["twitter_access_token_enc"] = None
        data["twitter_access_token_secret_enc"] = None
    elif oauth1_any:
        missing = [
            n
            for n, v in [
                ("twitter_api_key", k1),
                ("twitter_api_secret", s1),
                ("twitter_access_token", t1),
                ("twitter_access_token_secret", ts1),
            ]
            if not v
        ]
        if missing:
            raise ValueError(
                "OAuth 1.0a requires all four values (api key, api secret, access token, access token secret). "
                f"Missing: {', '.join(missing)}"
            )
        data["twitter_api_key_enc"] = encrypt_value(f, k1)
        data["twitter_api_secret_enc"] = encrypt_value(f, s1)
        data["twitter_access_token_enc"] = encrypt_value(f, t1)
        data["twitter_access_token_secret_enc"] = encrypt_value(f, ts1)
        data["twitter_oauth2_access_token_enc"] = None
        data["twitter_oauth2_refresh_token_enc"] = None

    acc = AccountDocument.model_validate(data)
    r.save(acc)
    return acc

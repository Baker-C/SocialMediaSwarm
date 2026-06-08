"""Merge HTTP account edit payloads into ``AccountDocument`` rows (no secrets in GET)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.account import AccountDocument, default_negative_semantics, default_system_prompt
from app.services.account_repository import AccountRepository
from app.services.twitter_oauth2_service import TwitterOAuth2Service
from app.services.voice_version_service import bump_voice_version_if_needed


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
    search_queries: list[str] | None = None
    voice_version_label: str | None = Field(default=None, max_length=120)


def account_edit_view(acc: AccountDocument, oauth: TwitterOAuth2Service | None = None) -> dict:
    """Safe JSON for the dashboard update-account form (no ciphertext or plaintext secrets)."""
    oauth_svc = oauth or TwitterOAuth2Service()
    status = oauth_svc.connection_status(acc.account_id)
    niche = acc.niche or ""
    mode = "oauth2" if status.connected else "none"
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
        "oauth_connected": status.connected,
        "oauth_expires_at": status.expires_at,
        "search_queries": list(acc.search_queries or []),
    }


def apply_account_update(account_id: str, body: AccountUpdateBody, repo: AccountRepository | None = None) -> AccountDocument:
    aid = (account_id or "").strip()
    if not aid:
        raise ValueError("account_id is required")

    r = repo or AccountRepository()
    existing = r.load(aid)
    if existing is None:
        raise LookupError("Account not found")

    data = existing.model_dump()
    profile = data.setdefault("profile", {})
    voice = data.setdefault("voice", {})

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

    if body.search_queries is not None:
        profile["search_queries"] = [s.strip() for s in body.search_queries if s and str(s).strip()]

    previous_hash = existing.voice_version_hash
    acc = AccountDocument.model_validate(data)
    acc = bump_voice_version_if_needed(
        acc,
        previous_hash=previous_hash,
        manual_label=body.voice_version_label,
    )
    r.save(acc)
    return acc

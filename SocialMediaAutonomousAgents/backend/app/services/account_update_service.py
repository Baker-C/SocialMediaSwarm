"""Merge HTTP account edit payloads into ``AccountDocument`` rows (no secrets in GET)."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.account import (
    AccountDocument,
    ContrastPattern,
    PunctuationRule,
    default_contrast_patterns,
    default_punctuation_rules,
    default_system_prompt,
)
from app.services.account_repository import AccountRepository
from app.services.twitter_oauth2_service import TwitterOAuth2Service
from app.services.voice_version_service import bump_voice_version_if_needed


class AccountUpdateBody(BaseModel):
    """PATCH body: ``None`` / omitted fields leave existing document values unchanged."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    category: str | None = Field(
        default=None, max_length=2000, validation_alias=AliasChoices("category", "niche")
    )
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)
    # Soft-retire flag. Retired accounts are excluded by default from the scheduler
    # and account listings; the document is kept (never deleted).
    retired: bool | None = None

    # ── Soul fields ──
    posting_prompt: str | None = Field(default=None, max_length=32000)   # was system_prompt
    personality: str | None = Field(default=None, max_length=16000)
    contrast_patterns: list[ContrastPattern] | None = None               # was negative_semantics
    punctuation_rules: list[PunctuationRule] | None = None               # NEW

    followers: int | None = Field(default=None, ge=0)
    posts_total: int | None = Field(default=None, ge=0)
    voice_version_label: str | None = Field(default=None, max_length=120)


def account_edit_view(acc: AccountDocument, oauth: TwitterOAuth2Service | None = None) -> dict:
    """Safe JSON for the dashboard edit form (no secrets). Returns the full soul."""
    oauth_svc = oauth or TwitterOAuth2Service()
    status = oauth_svc.connection_status(acc.account_id)
    category = acc.category or ""
    mode = "oauth2" if status.connected else "none"
    return {
        "account_id": acc.account_id,
        "category": category,
        "niches": [n.model_dump() for n in acc.niches],
        "twitter_handle": acc.twitter_handle or "",
        "status": acc.status or "active",
        "retired": acc.retired,
        # ── Soul ──
        "posting_prompt": (acc.posting_prompt or "").strip() or default_system_prompt(category),
        "personality": (acc.personality or "").strip(),
        "contrast_patterns": [p.model_dump() for p in (acc.contrast_patterns or [])]
            or default_contrast_patterns(),
        "punctuation_rules": [r.model_dump() for r in (acc.punctuation_rules or [])]
            or default_punctuation_rules(),
        # ── version + profile/oauth ──
        "voice_version_label": acc.voice_version_label,
        "voice_version_seq": acc.voice_version_seq,
        "voice_version_hash": acc.voice_version_hash,
        "followers": acc.followers,
        "posts_total": acc.posts_total,
        "registered_at": acc.registered_at,
        "last_interval_slot": acc.last_interval_slot,
        "last_post_id": acc.last_post_id,
        "credential_mode": mode,
        "oauth_connected": status.connected,
        "oauth_expires_at": status.expires_at,
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
    soul = data.setdefault("soul", {})          # write into soul, not voice

    if body.category is not None:
        soul["category"] = body.category.strip() or existing.category or aid
    niche = soul.get("category") or existing.category or aid

    if body.twitter_handle is not None:
        profile["twitter_handle"] = body.twitter_handle.strip()
    if body.status is not None:
        profile["status"] = (body.status or "active").strip() or "active"
    if body.retired is not None:
        profile["retired"] = bool(body.retired)

    # ── Soul updates ──
    if body.posting_prompt is not None:
        sp = body.posting_prompt.strip()
        soul["posting_prompt"] = sp if sp else default_system_prompt(niche)

    if body.personality is not None:
        soul["personality"] = body.personality.strip()

    if body.contrast_patterns is not None:
        cleaned = [p.model_dump() for p in body.contrast_patterns if (p.text or "").strip()]
        soul["contrast_patterns"] = cleaned if cleaned else default_contrast_patterns()

    if body.punctuation_rules is not None:
        cleaned = [r_.model_dump() for r_ in body.punctuation_rules if (r_.pattern or "").strip()]
        soul["punctuation_rules"] = cleaned if cleaned else default_punctuation_rules()

    if body.followers is not None:
        profile["followers"] = body.followers
    if body.posts_total is not None:
        profile["posts_total"] = body.posts_total

    previous_hash = existing.voice_version_hash
    acc = AccountDocument.model_validate(data)
    acc = bump_voice_version_if_needed(
        acc,
        previous_hash=previous_hash,
        manual_label=body.voice_version_label,
    )
    r.save(acc)
    return acc

# Task 03 — Services & API (update + create + edit view)

## Task Overview

**Files:**
- `SocialMediaAutonomousAgents/backend/app/services/account_update_service.py`
- `SocialMediaAutonomousAgents/backend/app/services/account_create_service.py`

These are the HTTP-facing services behind the account routes (`app/api/routes/accounts.py`, unchanged):
- `PATCH /accounts/{id}` → `AccountUpdateBody` → `apply_account_update`
- `GET /accounts/{id}/edit` → `account_edit_view` (consumed by the frontend `fetchAccountVoice`)
- `POST /accounts` → `AccountCreateBody` → `apply_account_create`

They must accept and return the soul fields (`personality`, `posting_prompt`, `contrast_patterns`, `punctuation_rules`) and stop using `negative_semantics`/`system_prompt`.

**What it affects**
- The edit payload the Voice tab / settings form reads (`AccountVoiceDetail`, Task 08).
- The PATCH contract used to edit soul fields.
- Version bump on edit (via `apply_account_update` → `r.save()` → Task 05).

**Dependencies:** Tasks 01 (model + defaults), 04 (repository), 05 (versioning).

---

## Proposed Solution

### a. Summary
1. `AccountUpdateBody`: replace `system_prompt`/`negative_semantics` with `posting_prompt`/`contrast_patterns`/`punctuation_rules` (keep `personality`). Use typed list items where practical (`list[ContrastPattern]`, `list[PunctuationRule]`) so FastAPI validates the request body.
2. `apply_account_update`: write into `soul` (the merged `data["soul"]` dict), fall back to defaults on empty, then `bump_voice_version_if_needed` (unchanged call).
3. `account_edit_view`: return the four soul fields (typed → dumped to dicts), seeding `posting_prompt` from the niche default when empty.
4. `account_create_service`: mirror the renamed fields so creation can set initial soul.

### b. BEFORE — `account_update_service.py` (key regions)

```python
from app.models.account import AccountDocument, default_negative_semantics, default_system_prompt
from app.services.voice_version_service import bump_voice_version_if_needed


class AccountUpdateBody(BaseModel):
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


def account_edit_view(acc, oauth=None) -> dict:
    # …
    return {
        # …
        "system_prompt": (acc.system_prompt or "").strip() or default_system_prompt(niche),
        "personality": (acc.personality or "").strip(),
        "negative_semantics": list(acc.negative_semantics or default_negative_semantics()),
        # …
    }


def apply_account_update(account_id, body, repo=None) -> AccountDocument:
    # … load existing; data = existing.model_dump(); voice = data.setdefault("voice", {}) …
    if body.system_prompt is not None:
        sp = body.system_prompt.strip()
        voice["system_prompt"] = sp if sp else default_system_prompt(niche)
    if body.personality is not None:
        voice["personality"] = body.personality.strip()
    if body.negative_semantics is not None:
        cleaned = [s.strip() for s in body.negative_semantics if s and str(s).strip()]
        voice["negative_semantics"] = cleaned if cleaned else default_negative_semantics()
    # … followers/posts_total/search_queries …
    previous_hash = existing.voice_version_hash
    acc = AccountDocument.model_validate(data)
    acc = bump_voice_version_if_needed(acc, previous_hash=previous_hash, manual_label=body.voice_version_label)
    r.save(acc)
    return acc
```

### c. AFTER — `account_update_service.py`

```python
"""Merge HTTP account edit payloads into AccountDocument rows (no secrets in GET)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.account import (
    AccountDocument, ContrastPattern, PunctuationRule,
    default_contrast_patterns, default_punctuation_rules, default_system_prompt,
)
from app.services.account_repository import AccountRepository
from app.services.twitter_oauth2_service import TwitterOAuth2Service
from app.services.voice_version_service import bump_voice_version_if_needed


class AccountUpdateBody(BaseModel):
    """PATCH body: None / omitted fields leave existing values unchanged."""
    model_config = ConfigDict(extra="ignore")

    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)

    # ── Soul fields ──
    posting_prompt: str | None = Field(default=None, max_length=32000)   # was system_prompt
    personality: str | None = Field(default=None, max_length=16000)
    contrast_patterns: list[ContrastPattern] | None = None               # was negative_semantics
    punctuation_rules: list[PunctuationRule] | None = None               # NEW

    followers: int | None = Field(default=None, ge=0)
    posts_total: int | None = Field(default=None, ge=0)
    search_queries: list[str] | None = None
    voice_version_label: str | None = Field(default=None, max_length=120)


def account_edit_view(acc: AccountDocument, oauth: TwitterOAuth2Service | None = None) -> dict:
    """Safe JSON for the dashboard edit form (no secrets). Returns the full soul."""
    oauth_svc = oauth or TwitterOAuth2Service()
    status = oauth_svc.connection_status(acc.account_id)
    niche = acc.niche or ""
    mode = "oauth2" if status.connected else "none"
    return {
        "account_id": acc.account_id,
        "niche": niche,
        "twitter_handle": acc.twitter_handle or "",
        "status": acc.status or "active",
        # ── Soul ──
        "posting_prompt": (acc.posting_prompt or "").strip() or default_system_prompt(niche),
        "personality": (acc.personality or "").strip(),
        "contrast_patterns": [p.model_dump() for p in (acc.contrast_patterns or [])]
            or default_contrast_patterns(),
        "punctuation_rules": [r.model_dump() for r in (acc.punctuation_rules or [])]
            or default_punctuation_rules(),
        # ── version + profile/oauth (unchanged) ──
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
        "search_queries": list(acc.search_queries or []),
    }


def apply_account_update(account_id, body, repo=None) -> AccountDocument:
    aid = (account_id or "").strip()
    if not aid:
        raise ValueError("account_id is required")
    r = repo or AccountRepository()
    existing = r.load(aid)
    if existing is None:
        raise LookupError("Account not found")

    data = existing.model_dump()
    profile = data.setdefault("profile", {})
    soul = data.setdefault("soul", {})          # CHANGED: write into soul, not voice

    if body.niche is not None:
        profile["niche"] = body.niche.strip() or existing.niche or aid
    niche = profile.get("niche") or existing.niche or aid

    if body.twitter_handle is not None:
        profile["twitter_handle"] = body.twitter_handle.strip()
    if body.status is not None:
        profile["status"] = (body.status or "active").strip() or "active"

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
    if body.search_queries is not None:
        profile["search_queries"] = [s.strip() for s in body.search_queries if s and str(s).strip()]

    previous_hash = existing.voice_version_hash
    acc = AccountDocument.model_validate(data)
    acc = bump_voice_version_if_needed(acc, previous_hash=previous_hash, manual_label=body.voice_version_label)
    r.save(acc)
    return acc
```

### d. AFTER — `account_create_service.py` (only the field renames)

```python
class AccountCreateBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    account_id: str = Field(min_length=1, max_length=500)
    niche: str | None = Field(default=None, max_length=2000)
    twitter_handle: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default="active", max_length=64)
    posting_prompt: str | None = Field(default=None, max_length=32000)   # was system_prompt
    personality: str | None = Field(default=None, max_length=16000)
    contrast_patterns: list | None = None                                # was negative_semantics
    punctuation_rules: list | None = None                                # NEW


def apply_account_create(body, repo=None) -> AccountDocument:
    # … unchanged through run_create_account_job (which seeds default_soul via upsert_profile) …
    profile_fields = (body.status, body.posting_prompt, body.personality,
                      body.contrast_patterns, body.punctuation_rules)
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
```

### e. Written explanation
The update service is where the soul becomes user-editable over HTTP. By typing the request fields as `list[ContrastPattern]`/`list[PunctuationRule]`, FastAPI validates incoming JSON (rejecting e.g. `correlation: "maybe"`) before we touch the document. Each field follows the established "None means leave alone; empty means reset to default" convention, mirroring the old `negative_semantics` behavior.

`account_edit_view` is the exact payload the frontend's `fetchAccountVoice` reads (it hits `/edit`). Returning all four soul fields (plus the version stamp) is what lets Task 08 render the full soul without any extra endpoint. We `model_dump()` the typed lists to plain dicts so the JSON shape is stable and framework-agnostic.

Creation simply forwards the renamed fields; the actual default soul is seeded in `upsert_profile` (Task 04), so an account created with no soul overrides still gets a complete, valid soul.

---

## Decision Defense

**Why type the PATCH body items (`list[ContrastPattern]`) instead of accepting `list[dict]`?**
Validation at the edge. A malformed pattern (missing `text`, bad `correlation`) is rejected with a 422 before it can corrupt a stored document or crash the dashboard renderer. It also self-documents the API in the OpenAPI schema.

**Why reuse the existing `/edit` payload rather than add a `/soul` endpoint?**
The frontend already fetches `/edit` for voice display, and the settings form already PATCHes the same shape. Extending the existing contract keeps one round-trip and avoids endpoint sprawl. (`/api/voice-polish-rules`, added earlier as a stopgap, is deleted in Task 06 since rules are now per-account.)

**Why keep `voice_version_label` as a manual override field?**
It lets an operator name a version ("snarkier-v2") without changing content. The hash logic (Task 05) already supports a manual label independent of content changes; preserving the field keeps that capability.

**Why fall back to defaults on empty lists rather than allowing an empty soul?**
An account with zero contrast patterns or zero punctuation rules is almost always an accident (e.g. a form cleared everything). Defaulting protects output quality; an operator who truly wants "no rules" can express that via personality/posting prompt.

---

## Test fix owned by this task (post-review correction)

`tests/unit/test_account_update_service.py::test_account_edit_view_has_no_encrypted_fields` asserts `isinstance(view["negative_semantics"], list)` and `len(view["negative_semantics"]) >= 1`. `account_edit_view` no longer returns that key. Update the assertions to the new payload:
```python
assert isinstance(view["contrast_patterns"], list) and len(view["contrast_patterns"]) >= 1
assert isinstance(view["punctuation_rules"], list) and len(view["punctuation_rules"]) >= 1
assert "posting_prompt" in view
assert "system_prompt" not in view and "negative_semantics" not in view
```

## Frontend interaction (for reference; full detail in `08-frontend.md`)
The edited fields are surfaced on the **Settings** form (route `/accounts/{id}/settings`, reached via the "Current: vN" badge at the top-right of the Voice tab) and displayed read-only on the **Voice** tab. After a PATCH, the "Current: vN" badge increments and a new revision appears in the timeline.

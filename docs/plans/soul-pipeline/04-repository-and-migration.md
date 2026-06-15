# Task 04 — Repository + Migration

## Task Overview

**File:** `SocialMediaAutonomousAgents/backend/app/services/account_repository.py`
**Plus:** new one-time script `SocialMediaAutonomousAgents/backend/scripts/migrate_voice_to_soul.py`

The repository is the read/write boundary to RavenDB. Three functions need updating:
- `normalize_account_document(raw)` — maps a raw RavenDB dict into the `{account_id, profile, voice, posting}` shape before validation. Must now emit `soul` (not `voice`).
- `account_to_document(account)` — serializes back to a dict for storage. Must stop emitting `voice` and stop the `negative_semantics`/`system_prompt` backfills (those defaults now live in the soul defaults / migration helper).
- `AccountRepository.upsert_profile(...)` — creates new accounts. Must initialize `soul` via `default_soul(niche)` instead of `AccountVoice(...)`.

**What it affects**
- Every account load/save (the lone `JohnJames_News` doc migrates to `soul` on first save).
- New-account creation (`create_account_job` → `upsert_profile`).
- `save()` already calls `bump_voice_version_if_needed` (Task 05) — no change there beyond it now hashing the full soul.

**Dependencies:** Tasks 01 (model + `default_soul`, `_soul_from_legacy`), 05 (versioning import). This file currently imports `AccountVoice`, `default_negative_semantics`, `default_system_prompt` — update imports.

> **Note on redundancy:** With Task 01's `_lift_legacy_fields` validator handling migration, `normalize_account_document` is partly belt-and-suspenders. We keep it because `document_to_account` calls it explicitly and other call sites rely on its flattening; we simplify it to delegate soul-building to the model's `_soul_from_legacy` helper to avoid two copies of the mapping logic.

---

## Proposed Solution

### a. Summary
1. Update imports (`AccountSoul`, `default_soul`, `_soul_from_legacy` — or re-validate via `AccountDocument`).
2. `normalize_account_document`: build `soul` (from `soul` if present, else legacy `voice`/flat) and drop the `voice` branch.
3. `account_to_document`: remove `voice` backfills; ensure `soul.posting_prompt` is seeded when empty; never write a `voice` key.
4. `upsert_profile`: use `soul=default_soul(niche or account_id)`.
5. Add migration script that loads each account and re-saves (the validator + serializer do the conversion) — explicit, logged, idempotent.

### b. BEFORE — key regions of `app/services/account_repository.py`

```python
from app.models.account import (
    AccountDocument, AccountPostingState, AccountProfile, AccountVoice,
    default_negative_semantics, default_system_prompt,
)
from app.services.voice_version_service import bump_voice_version_if_needed


def normalize_account_document(raw: dict) -> dict:
    d = _strip_metadata(raw)
    profile = dict(d.get("profile") or {})
    voice = dict(d.get("voice") or {})
    posting = dict(d.get("posting") or {})
    # … profile.setdefault(...) …
    voice.setdefault("system_prompt", d.get("system_prompt") or "")
    voice.setdefault("personality", d.get("personality") or "")
    voice.setdefault("voice_version_hash", d.get("voice_version_hash"))
    voice.setdefault("voice_version_seq", int(d.get("voice_version_seq") or 1))
    voice.setdefault("voice_version_label", d.get("voice_version_label") or "v1")
    neg = voice.get("negative_semantics") or d.get("negative_semantics")
    voice["negative_semantics"] = list(neg) if neg else default_negative_semantics()
    # … posting.setdefault(...) …
    return {"account_id": d.get("account_id"), "profile": profile, "voice": voice, "posting": posting}


def account_to_document(account: AccountDocument) -> dict:
    d = account.model_dump(exclude_none=True)
    d.pop("@metadata", None)
    profile = d.setdefault("profile", {})
    voice = d.setdefault("voice", {})
    if not voice.get("system_prompt"):
        voice["system_prompt"] = default_system_prompt(profile.get("niche") or account.account_id)
    if not voice.get("negative_semantics"):
        voice["negative_semantics"] = default_negative_semantics()
    return d


class AccountRepository:
    # …
    def upsert_profile(self, account_id, *, niche=None, twitter_handle=None, status=None):
        existing = self.load(account_id)
        if existing is None:
            now = datetime.now(timezone.utc).isoformat()
            acc = AccountDocument(
                account_id=account_id,
                profile=AccountProfile(niche=niche or account_id, twitter_handle=twitter_handle or "",
                                       status=status or "active", registered_at=now, followers_when_registered=0),
                voice=AccountVoice(system_prompt=default_system_prompt(niche or account_id),
                                   negative_semantics=default_negative_semantics()),
                posting=AccountPostingState(),
            )
        else:
            # … merge profile fields …
            acc = AccountDocument.model_validate(data)
        self.save(acc)
        return acc
```

### c. AFTER — key regions of `app/services/account_repository.py`

```python
from app.models.account import (
    AccountDocument, AccountPostingState, AccountProfile,
    default_soul, default_system_prompt, _soul_from_legacy,  # AccountVoice & default_negative_semantics removed
)
from app.services.voice_version_service import bump_voice_version_if_needed


def normalize_account_document(raw: dict) -> dict:
    """Map any historical RavenDB shape into {account_id, profile, soul, posting}.
    Soul construction is delegated to the model's _soul_from_legacy so there is ONE
    mapping of legacy fields → soul (no drift between repo and model)."""
    d = _strip_metadata(raw)
    profile = dict(d.get("profile") or {})
    posting = dict(d.get("posting") or {})

    profile.setdefault("niche", d.get("niche") or d.get("account_id") or "")
    profile.setdefault("twitter_handle", d.get("twitter_handle") or "")
    profile.setdefault("status", d.get("status") or "active")
    profile.setdefault("followers", int(d.get("followers") or 0))
    profile.setdefault("posts_total", int(d.get("posts_total") or 0))
    profile.setdefault("registered_at", d.get("registered_at"))
    profile.setdefault("followers_when_registered", d.get("followers_when_registered"))
    sq = profile.get("search_queries")
    if sq is None:
        sq = d.get("search_queries")
    profile["search_queries"] = list(sq or [])

    # Soul: prefer an existing nested soul; else migrate from legacy `voice`; else from flat keys.
    if d.get("soul"):
        soul = dict(d["soul"])
    elif d.get("voice"):
        soul = _soul_from_legacy(dict(d["voice"]))   # legacy nested voice object
    else:
        soul = _soul_from_legacy(d)                   # very old flat document

    slot = posting.get("last_interval_slot") or d.get("last_interval_slot") or d.get("last_post_slot")
    posting.setdefault("last_interval_slot", slot)
    posting.setdefault("last_post_id", d.get("last_post_id"))
    posting.setdefault("last_post_text", d.get("last_post_text"))
    posting.setdefault("last_post_at", d.get("last_post_at"))
    posting.setdefault("last_post_views", d.get("last_post_views"))
    copied = posting.get("copied_reference_tweet_ids")
    if copied is None:
        copied = d.get("copied_reference_tweet_ids")
    posting["copied_reference_tweet_ids"] = list(copied or [])

    return {
        "account_id": d.get("account_id"),
        "profile": profile,
        "soul": soul,           # CHANGED: emit soul, not voice
        "posting": posting,
    }


def account_to_document(account: AccountDocument) -> dict:
    """Serialize for storage. Soul is canonical; we never write a `voice` key.
    Seed posting_prompt from the niche if somehow empty (keeps composes deterministic)."""
    d = account.model_dump(exclude_none=True)
    d.pop("@metadata", None)
    d.pop("voice", None)                       # NEW: ensure no deprecated object is persisted
    profile = d.setdefault("profile", {})
    soul = d.setdefault("soul", {})
    if not soul.get("posting_prompt"):         # CHANGED: seed posting_prompt (was voice.system_prompt)
        soul["posting_prompt"] = default_system_prompt(profile.get("niche") or account.account_id)
    # NOTE: no negative_semantics backfill — contrast_patterns default via the model's factory.
    return d


class AccountRepository:
    # … load/save/list_* unchanged except save() now hashes full soul via Task 05 …

    def upsert_profile(self, account_id, *, niche=None, twitter_handle=None, status=None):
        existing = self.load(account_id)
        if existing is None:
            now = datetime.now(timezone.utc).isoformat()
            acc = AccountDocument(
                account_id=account_id,
                profile=AccountProfile(
                    niche=niche or account_id,
                    twitter_handle=twitter_handle or "",
                    status=status or "active",
                    registered_at=now,
                    followers_when_registered=0,
                ),
                soul=default_soul(niche or account_id),   # CHANGED: full default soul
                posting=AccountPostingState(),
            )
        else:
            data = existing.model_dump()
            profile = data.setdefault("profile", {})
            if niche is not None:
                profile["niche"] = niche
            if twitter_handle is not None:
                profile["twitter_handle"] = twitter_handle
            if status is not None:
                profile["status"] = status
            if profile.get("registered_at") is None:
                profile["registered_at"] = datetime.now(timezone.utc).isoformat()
            if profile.get("followers_when_registered") is None:
                profile["followers_when_registered"] = int(profile.get("followers") or 0)
            acc = AccountDocument.model_validate(data)
        self.save(acc)
        return acc
```

### d. NEW — `backend/scripts/migrate_voice_to_soul.py`

```python
"""One-time migration: rewrite every account document so `voice` → `soul`.

Idempotent: loading applies the validator (voice→soul) and saving drops `voice`
and stamps the soul version. Safe to re-run. Run inside the backend container:

    docker exec -it social-media-backend python -m scripts.migrate_voice_to_soul
"""

from __future__ import annotations

import logging

from app.services.account_repository import AccountRepository

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("migrate_voice_to_soul")


def main() -> None:
    repo = AccountRepository()
    accounts = repo.list_all_accounts()
    log.info("Found %d account(s) to migrate", len(accounts))
    for acc in accounts:
        # load() already ran the validator → acc.soul is populated, voice dropped.
        # NOTE (post-review): the FIRST save legitimately bumps the version. Task 05
        # changes the hash payload from {system_prompt, personality} to the full soul,
        # so the freshly-computed hash will not match the old stored hash and seq bumps
        # once. That is desirable provenance, not a bug — label it so the timeline reads
        # clearly. We must NOT pass manual_label unconditionally: a manual label forces
        # `changed=True` on every call, which would write a duplicate revision on each
        # re-run and break idempotency. So label ONLY when a real bump is pending.
        from app.services.voice_version_service import (
            bump_voice_version_if_needed,
            compute_voice_hash,
        )
        pending = (acc.voice_version_hash or "") != compute_voice_hash(
            posting_prompt=acc.posting_prompt,
            personality=acc.personality,
            contrast_patterns=acc.contrast_patterns,
            punctuation_rules=acc.punctuation_rules,
        )
        bump_voice_version_if_needed(
            acc,
            previous_hash=acc.voice_version_hash,
            manual_label="soul-migration" if pending else None,
        )
        repo.save(acc)  # serializer omits `voice`; save() also calls bump (now a no-op).
        log.info(
            "Migrated %s → soul (version=%s seq=%s, %d contrast, %d punctuation)",
            acc.account_id,
            acc.voice_version_label,
            acc.voice_version_seq,
            len(acc.contrast_patterns or []),
            len(acc.punctuation_rules or []),
        )
    log.info("Migration complete.")


if __name__ == "__main__":
    main()
```

### e. Written explanation
After Task 01, simply loading and re-saving any account performs the migration: `load()` runs the validator (legacy `voice`/flat → `soul`), and `save()` serializes with `account_to_document` (which now strips `voice`) and stamps the version. The migration script makes that explicit and logged so we don't rely on incidental writes.

The single biggest correctness point is `account_to_document` popping `voice` — without it, `model_dump()` of an `AccountDocument` that still carried a residual `voice` (it won't, since the field is removed in Task 01) or any stray serialization could persist stale data. Popping defensively keeps stored documents clean.

`normalize_account_document` is reduced to delegating soul construction to `_soul_from_legacy`, so the legacy-field mapping exists in exactly one place (the model). This avoids the classic bug where the repo and the model disagree on how to migrate.

---

## Decision Defense

**Why keep `normalize_account_document` at all if the model validator already migrates?**
`document_to_account` and other readers call it directly, and it also flattens `profile`/`posting` defaults the validator's "already nested" fast-path skips. Removing it is a larger refactor with little upside. Delegating its soul logic to `_soul_from_legacy` removes the duplication risk while preserving the existing call contract.

**Why an explicit migration script instead of trusting lazy migration on next save?**
The lone account is written frequently (every post stamps `posting.last_*` and triggers `save()`), so lazy migration would happen quickly — but "quickly" is not "deterministically." A one-shot, logged, idempotent script lets us migrate on demand, verify the result immediately (Task 09), and re-run safely if needed.

**Why is the first run not a true no-op, and how is "idempotent" still true? (post-review)**
The migration changes the hash *payload* (Task 05 hashes the full soul, not just `system_prompt`+`personality`), so the first run necessarily bumps the version once and writes a single `soul-migration` revision. Every subsequent run computes the same hash, finds it unchanged, and — because we only pass `manual_label` when a bump is genuinely pending — performs no further bump and writes no further revision. So "idempotent" means *converges after the first run*, not *zero effect on the first run*. The same one-time bump also occurs under lazy migration (first post after deploy), which is exactly why running the explicit script first makes the event deterministic and clearly labeled.

**Why seed `posting_prompt` in the serializer rather than only at creation?**
Defense in depth: a post composer must never receive an empty posting prompt. Seeding from the niche at write time guarantees every stored document has usable composition instructions even if an edit cleared the field.

**No frontend in this task.**

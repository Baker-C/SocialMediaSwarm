# Task 05 — Soul Versioning (hash all soul fields)

## Task Overview

**File:** `SocialMediaAutonomousAgents/backend/app/services/voice_version_service.py`

`bump_voice_version_if_needed` computes a hash of the writing identity and, when it changes, bumps `voice_version_seq`, relabels (`vN`), and writes a `VoiceRevisionDocument`. Today the hash covers only `system_prompt` + `personality`, so edits to `negative_semantics` (and, after this feature, to `contrast_patterns`/`punctuation_rules`) would **not** create a new version. We extend the hash to cover the full soul and persist the full soul into each revision.

**What it affects**
- Called from `AccountRepository.save()` (Task 04) on every account write.
- Writes `VoiceRevisionDocument` (Task 02 shape).
- Drives `voice_version_seq/label/hash` shown on the Voice tab and in `AccountSummary`.

**Dependency:** Tasks 01 (soul fields/accessors) and 02 (revision shape).

---

## Proposed Solution

### a. Summary
1. `compute_voice_hash` gains `contrast_patterns` + `punctuation_rules` params and folds them into the canonical JSON payload.
2. `bump_voice_version_if_needed` reads all four soul fields off the account and passes them through; the revision it writes carries the full soul snapshot (posting_prompt, personality, contrast_patterns, punctuation_rules) instead of system_prompt/personality/negative_semantics.

### b. BEFORE — `app/services/voice_version_service.py`

```python
def compute_voice_hash(*, system_prompt: str, personality: str) -> str:
    payload = {"system_prompt": (system_prompt or "").strip(), "personality": (personality or "").strip()}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_voice_version_if_needed(account, *, previous_hash, manual_label=None, revision_repo=None):
    current_hash = compute_voice_hash(system_prompt=account.system_prompt, personality=account.personality)
    prev = (previous_hash or "").strip() or (account.voice_version_hash or "").strip()
    manual = (manual_label or "").strip()
    changed = False
    # … seq/label bump logic (unchanged) …
    repo = revision_repo or VoiceRevisionRepository()
    repo.save(
        VoiceRevisionDocument(
            account_id=account.account_id,
            seq=seq,
            label=account.voice_version_label or f"v{seq}",
            version_hash=account.voice_version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
            system_prompt=(account.system_prompt or "").strip(),
            personality=(account.personality or "").strip(),
            negative_semantics=list(account.negative_semantics or []),
        )
    )
    return account
```

### c. AFTER — `app/services/voice_version_service.py`

```python
"""Version and stamp account soul revisions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.account import AccountDocument
from app.models.voice_revision import VoiceRevisionDocument
from app.services.voice_revision_repository import VoiceRevisionRepository


def _normalize_patterns(patterns) -> list[dict]:
    """Stable, comparable representation of a list of pydantic models or dicts,
    used both for hashing and for archiving.

    The digest is intentionally ORDER-SENSITIVE: list order is preserved here, so
    reordering patterns is treated as a real (auditable) change and bumps the version.
    Determinism across Python dict-ordering comes from json.dumps(sort_keys=True) in
    compute_voice_hash sorting the *dict keys* — NOT from sorting this list."""
    out: list[dict] = []
    for p in patterns or []:
        d = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        out.append(d)
    return out


def compute_voice_hash(
    *,
    posting_prompt: str,
    personality: str,
    contrast_patterns=None,      # NEW: list[ContrastPattern] | list[dict]
    punctuation_rules=None,      # NEW: list[PunctuationRule] | list[dict]
) -> str:
    """SHA256 over the FULL soul so any edit (prompt, personality, a single pattern,
    a single rule) produces a new version. Canonical JSON (sorted keys) → stable digest."""
    payload = {
        "posting_prompt": (posting_prompt or "").strip(),
        "personality": (personality or "").strip(),
        "contrast_patterns": _normalize_patterns(contrast_patterns),
        "punctuation_rules": _normalize_patterns(punctuation_rules),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_voice_version_if_needed(
    account: AccountDocument,
    *,
    previous_hash: str | None,
    manual_label: str | None = None,
    revision_repo: VoiceRevisionRepository | None = None,
) -> AccountDocument:
    # Hash the whole soul (accessors proxy to account.soul.*).
    current_hash = compute_voice_hash(
        posting_prompt=account.posting_prompt,
        personality=account.personality,
        contrast_patterns=account.contrast_patterns,   # NEW
        punctuation_rules=account.punctuation_rules,    # NEW
    )
    prev = (previous_hash or "").strip() or (account.voice_version_hash or "").strip()
    manual = (manual_label or "").strip()
    changed = False

    if not prev:
        seq = max(1, int(account.voice_version_seq or 1))
        account.voice_version_seq = seq
        account.voice_version_hash = current_hash
        account.voice_version_label = manual or (account.voice_version_label or "").strip() or f"v{seq}"
        changed = True
    elif prev == current_hash and not manual:
        return account
    else:
        if prev != current_hash:
            seq = max(1, int(account.voice_version_seq or 1)) + 1
            account.voice_version_seq = seq
            account.voice_version_label = f"v{seq}"
            account.voice_version_hash = current_hash
            changed = True
        if manual:
            account.voice_version_label = manual
            changed = True

    if not changed:
        return account

    seq = max(1, int(account.voice_version_seq or 1))
    repo = revision_repo or VoiceRevisionRepository()
    repo.save(
        VoiceRevisionDocument(
            account_id=account.account_id,
            seq=seq,
            label=account.voice_version_label or f"v{seq}",
            version_hash=account.voice_version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
            # Full soul snapshot (Task 02 shape):
            personality=(account.personality or "").strip(),
            posting_prompt=(account.posting_prompt or "").strip(),
            contrast_patterns=list(account.contrast_patterns or []),
            punctuation_rules=list(account.punctuation_rules or []),
        )
    )
    return account
```

### d. Written explanation
The seq/label bump logic is unchanged — only the **inputs** to the hash and the **payload** of the revision change. `_normalize_patterns` guarantees a deterministic digest whether the caller passes pydantic models (normal account save) or plain dicts (e.g. a test). Sorting keys inside the JSON dump (already present) keeps the digest stable across Python dict-ordering.

Because the hash now covers `contrast_patterns` and `punctuation_rules`, editing a single pattern through the PATCH endpoint (Task 03) will correctly produce `v2`, write a revision, and surface on the timeline.

---

## Decision Defense

**Why include `punctuation_rules` in the version hash even though they're "just formatting"?**
They are part of the account's writing identity and are user-editable. If someone changes how punctuation is normalized, that is a meaningful, auditable change to output. Excluding them would create silent, untracked drift between what the timeline claims and what actually shaped posts.

**Why a content hash rather than an explicit "dirty" flag from the API layer?**
A hash is self-correcting: it bumps if and only if content actually differs, regardless of which code path mutated the soul (API, migration, script). A manual dirty flag would have to be set perfectly at every write site — exactly the kind of bug we avoid.

**Test fix owned by this task (post-review correction):**
`tests/unit/test_voice_version_service.py` calls `compute_voice_hash(system_prompt=..., personality=...)` (lines ~25–28, 42, 58) and asserts `saved.system_prompt` / `saved.negative_semantics` (lines ~33, 35). The hash kwarg is renamed (`system_prompt → posting_prompt`) and those revision fields are gone (Task 02). Update the test in lockstep:
```python
# hash calls
out.voice_version_hash == compute_voice_hash(
    posting_prompt=out.posting_prompt, personality=out.personality,
    contrast_patterns=out.contrast_patterns, punctuation_rules=out.punctuation_rules,
)
# saved-revision assertions
assert saved.posting_prompt == "Write hot takes."
assert saved.personality == "Snappy left-leaning voice."
assert isinstance(saved.contrast_patterns, list)
```
This file is listed as expected-green in Task 09, so it must move with the signature change here.

**Why keep the field names `voice_version_*` instead of renaming to `soul_version_*`?**
Bounded blast radius (see `00-overview.md` §3). `voice_version_*` is referenced by the revision repo, `AccountSummary`, and the analytics `voiceComparison.ts` selector. Renaming is a clean follow-up but is intentionally out of scope to keep this change reviewable. The rename recipe: grep `voice_version_` across `backend/app` and `frontend/src`, rename in lockstep, and add a one-time read-shim in `normalize_account_document` for the old key.

**No frontend in this task.**

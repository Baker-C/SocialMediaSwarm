# Task 02 — Voice Revision Archive

## Task Overview

**File:** `SocialMediaAutonomousAgents/backend/app/models/voice_revision.py`

`VoiceRevisionDocument` is the append-only archive written every time an account's writing identity changes (see Task 05). One document per version: `voicerevisions/{account_id}-v{seq}`. Today it archives `system_prompt`, `personality`, `negative_semantics`. It must instead archive the full **soul** snapshot so history is complete and the Voice tab timeline can show exactly what the soul looked like at each version.

**What it affects**
- `voice_version_service.bump_voice_version_if_needed` (Task 05) constructs this document.
- `VoiceRevisionRepository.list_for_account` (unchanged) returns these to the API.
- `GET /api/accounts/{id}/voice-revisions` → frontend revision timeline (Task 08).

**Dependency:** Task 01 (imports default factories from `account.py`). This file currently imports `default_negative_semantics`, which Task 01 removes — so this file **will not compile until updated here**. Do 01 then 02.

---

## Proposed Solution

### a. Summary
Swap the legacy field set for the soul snapshot. Import the new default factories. Use typed lists (`list[ContrastPattern]`, `list[PunctuationRule]`) for validation, matching `AccountSoul`.

### b. BEFORE — `app/models/voice_revision.py`

```python
"""Voice revision history for account voice versioning."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.account import default_negative_semantics


class VoiceRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str
    system_prompt: str = ""
    personality: str = ""
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"voicerevisions/{account_id}-v{seq}"
```

### c. AFTER — `app/models/voice_revision.py`

```python
"""Soul revision history. One immutable document per soul version.

Each revision captures the COMPLETE soul state at the moment of a version bump,
so the dashboard timeline and any future rollback can reconstruct an exact past identity.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Import the soul building blocks (defined in Task 01).
from app.models.account import ContrastPattern, PunctuationRule


class VoiceRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str

    # ── Full soul snapshot (canonical going forward) ──
    # NOTE: unlike AccountSoul, the list fields default to EMPTY, not to the default
    # factories. A revision is an immutable archive; filling a missing field with
    # today's defaults would FABRICATE history (every old row would show the current
    # default contrast set). Empty + the legacy passthrough below lets the dashboard
    # render pre-refactor revisions faithfully (see 08-frontend SoulDetail fallback).
    personality: str = ""                              # prose identity at this version
    posting_prompt: str = ""                           # was system_prompt; structural instructions
    contrast_patterns: list[ContrastPattern] = Field(default_factory=list)
    punctuation_rules: list[PunctuationRule] = Field(default_factory=list)

    # ── Legacy passthrough (read-only) for revisions written before the soul refactor ──
    # Kept ONLY so historical rows round-trip and the frontend can map
    # system_prompt → posting_prompt and negative_semantics → [negative] contrast.
    # Never populated for NEW revisions (Task 05 writes the soul fields above).
    # Pydantic's default extra="ignore" would otherwise DROP these keys on read, so
    # they must be declared here for the old data to survive the load.
    system_prompt: str | None = None
    negative_semantics: list[str] | None = None

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"voicerevisions/{account_id}-v{seq}"
```

### d. Written explanation
The revision document mirrors `AccountSoul`'s payload fields (minus the version stamp, which is represented by `seq`/`label`/`version_hash`/`changed_at` columns already on the revision). Using the same typed models as `AccountSoul` means the snapshot validates identically and serializes to the same JSON the frontend already knows how to render.

Old revision documents in RavenDB (which have `system_prompt`/`negative_semantics` and lack the new fields) still load and render **faithfully**. Two things make that true, and both are corrections to the first draft of this task:
1. The new list fields default to **empty**, not to the default factories. If they defaulted to the factories, every historical revision would display the *current* default contrast set — fabricated history, not the real past identity.
2. `system_prompt`/`negative_semantics` are retained as **read-only passthrough** fields. Pydantic's default `extra="ignore"` would silently strip them on load, which would make the frontend's documented legacy fallback (`system_prompt → posting_prompt`, `negative_semantics → [negative] contrast`) impossible — the data would never reach the client. Declaring them preserves the round-trip.

We do **not** keep these legacy columns on the live `AccountDocument`/`AccountSoul` (Task 01 removed them there). The ambiguity Task 01 eliminated was about a *mutable* document having two authoritative fields. On an **immutable archive row**, a read-only historical column is just record-keeping, not ambiguity — new revisions never write it.

---

## Decision Defense

**Why a full snapshot instead of a diff against the previous revision?**
Revisions are read individually by the timeline and may later back a "restore this version" action. A self-contained snapshot answers "what was the entire soul at vN?" in one read. A diff chain would require walking history and is fragile if any link is missing.

**Why typed lists rather than `list[dict]` in the archive?**
Consistency with `AccountSoul` (Task 01) and validation-on-read. If a malformed pattern ever reached the archive, we want it rejected at the boundary, not surfaced as a render crash on the dashboard.

**Why no migration of existing revision rows?**
They are immutable history. Rewriting them would falsify the record. Forward compatibility is sufficient to keep them readable — but note (corrected from the first draft) that forward compatibility means **empty list defaults + declared legacy passthrough fields**, NOT default-factory fill. Default-factory fill would make every old row appear to carry today's default contrast/punctuation set, which is the opposite of faithful history.

**No frontend in this task** — see `08-frontend.md` for how revisions are displayed and the click path to reach them.

---

## Addendum — Account snapshot carries the soul too (post-review correction)

**Files:** `app/models/account_snapshot.py`, `app/services/account_snapshot_service.py`

`AccountSnapshotDocument` is the *other* place that archives the writing identity (alongside engagement totals). It is built by `create_account_snapshot`, which is reachable from a **live route** (`app/api/routes/accounts.py:117`) and the `take_snapshot_tool`. Today it reads `acc.negative_semantics` — the accessor Task 01 deletes — so without this fix the snapshot endpoint throws `AttributeError` (HTTP 500). The original plan never listed these files; this addendum closes that gap.

**`app/models/account_snapshot.py` — change the voice fields to the soul snapshot:**
```python
# BEFORE
    system_prompt: str = ""
    personality: str = ""
    negative_semantics: list[str] = Field(default_factory=list)

# AFTER  (mirror the revision: full soul snapshot, typed)
    personality: str = ""
    posting_prompt: str = ""                                  # was system_prompt
    contrast_patterns: list[ContrastPattern] = Field(default_factory=list)
    punctuation_rules: list[PunctuationRule] = Field(default_factory=list)
    # Read-only legacy passthrough for pre-refactor snapshots (same rationale as the revision).
    system_prompt: str | None = None
    negative_semantics: list[str] | None = None
```
(Add `from app.models.account import ContrastPattern, PunctuationRule`.)

**`app/services/account_snapshot_service.py` — read soul fields, not the removed accessor:**
```python
# BEFORE
        system_prompt=acc.system_prompt,
        personality=acc.personality,
        negative_semantics=list(acc.negative_semantics),

# AFTER
        posting_prompt=acc.posting_prompt,
        personality=acc.personality,
        contrast_patterns=list(acc.contrast_patterns or []),
        punctuation_rules=list(acc.punctuation_rules or []),
```

**Decision defense:** a snapshot and a revision capture the same thing — the account's identity at a moment in time — so they should speak the same soul vocabulary instead of maintaining a second, now-orphaned `negative_semantics` field set. Reusing `ContrastPattern`/`PunctuationRule` keeps validation and JSON shape identical across both archives.

## Test fix owned by this task

`tests/test_analytics_api.py` (`test_list_voice_revisions`, ~lines 150–169) constructs `VoiceRevisionDocument(system_prompt=..., negative_semantics=...)` and asserts the response `system_prompt`. With the new shape those still *load* (legacy passthrough), but new-vocabulary assertions are clearer: build the fixture with `posting_prompt`/`personality`/`contrast_patterns` and assert `body["revisions"][0]["posting_prompt"]`. Update this test alongside the model change so it stays green.

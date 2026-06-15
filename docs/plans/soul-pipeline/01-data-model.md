# Task 01 — Data Model: `AccountSoul`

## Task Overview

**File:** `SocialMediaAutonomousAgents/backend/app/models/account.py`

This is the foundational task; everything else imports from here. We introduce the `AccountSoul` model and two strongly-typed building blocks (`ContrastPattern`, `PunctuationRule`), add default factories, wire `soul` into `AccountDocument`, migrate legacy `voice`/flat documents into `soul` inside the existing `model_validator`, and re-point the backward-compat property accessors at `soul`.

**What it affects**
- Every account document read from / written to RavenDB (collection `Accounts`).
- The compatibility accessors (`account.system_prompt`, `account.personality`, `account.voice_version_*`) used across `runner.py`, services, and scripts.
- Downstream imports: `voice_revision.py` (Task 02), `account_repository.py` (Task 04), `voice_version_service.py` (Task 05), `account_update_service.py` (Task 03), compose pipeline (Task 06).

**Decisions applied here (from `00-overview.md`)**
- `soul` is the single source of truth. `AccountVoice` is **removed**.
- `negative_semantics` is **removed** from the model; its content migrates into `contrast_patterns` with `correlation="negative"`.
- `system_prompt` is renamed to `posting_prompt` on the new model. The `account.system_prompt` accessor is kept (pointing at `soul.posting_prompt`) so existing call sites keep working.
- Typed Pydantic sub-models, not `list[dict]`.

**Dependencies / ordering:** Do this first. Because `account_repository.py` and `voice_revision.py` currently `import default_negative_semantics` / `AccountVoice`, those imports must be updated in their own tasks (04, 02) — this task removes those symbols, so expect compile errors until 02 and 04 are done. Implement 01 → 02 → 04 back-to-back.

---

## Proposed Solution

### a. Summary of changes

1. Add `Literal` import.
2. Replace `default_negative_semantics()` + `format_negative_semantics_for_prompt()` with `default_contrast_patterns()` + `format_contrast_patterns_for_prompt()`.
3. Keep `default_system_prompt(niche)` but it now feeds `posting_prompt`.
4. Add `default_punctuation_rules()`.
5. Add `ContrastPattern`, `PunctuationRule`, `AccountSoul` models + a `default_soul(niche)` builder.
6. Remove `AccountVoice`.
7. `AccountDocument`: replace `voice` with `soul`; rewrite `_lift_legacy_fields` to migrate flat/`voice` docs into `soul`; re-point accessors.

### b. BEFORE — `app/models/account.py` (structure + key regions)

```python
"""Account document shape stored in RavenDB (collection Accounts)."""

from pydantic import AliasChoices, BaseModel, Field, model_validator


def default_negative_semantics() -> list[str]:
    """Phrases, structures, and stylistic tells to avoid in composed posts."""
    return [
        "\"It's not that, it's this\" / \"It's not X, it's Y\" false-dichotomy reframes",
        # … 9 items total …
        "Numbered lesson lists, thread voice, or \"Lesson:\" / \"Thread:\" openers",
    ]


def format_negative_semantics_for_prompt(items: list[str] | None) -> str:
    """Bullet block for compose prompts."""
    cleaned = [s.strip() for s in (items or []) if s and s.strip()]
    if not cleaned:
        cleaned = default_negative_semantics()
    return "\n".join(f"- {line}" for line in cleaned)


def default_system_prompt(niche: str) -> str:
    return (
        f"Generate a post about {niche}. "
        "Open with a shocked, opinionated hook (conversational, not newsy) and keep it as one long, "
        "almost run-on sentence with commas—not a chain of short separate sentences. "
        "Post length: 150-280 characters."
    )


class AccountProfile(BaseModel):
    niche: str
    # … unchanged …


class AccountVoice(BaseModel):
    system_prompt: str = Field(default="")
    personality: str = Field(default="")
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)
    voice_version_hash: str | None = None
    voice_version_seq: int = 1
    voice_version_label: str | None = "v1"


class AccountPostingState(BaseModel):
    # … unchanged …


class AccountDocument(BaseModel):
    account_id: str
    profile: AccountProfile
    voice: AccountVoice = Field(default_factory=AccountVoice)
    posting: AccountPostingState = Field(default_factory=AccountPostingState)

    @model_validator(mode="before")
    @classmethod
    def _lift_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if "profile" in value:
            return value
        return {
            "account_id": value.get("account_id"),
            "profile": { … },
            "voice": {
                "system_prompt": value.get("system_prompt") or "",
                "personality": value.get("personality") or "",
                "negative_semantics": value.get("negative_semantics") or default_negative_semantics(),
                "voice_version_hash": value.get("voice_version_hash"),
                "voice_version_seq": int(value.get("voice_version_seq") or 1),
                "voice_version_label": value.get("voice_version_label") or "v1",
            },
            "posting": { … },
        }

    # … ~dozens of @property accessors. The voice-related ones today read self.voice.* :
    @property
    def system_prompt(self) -> str:
        return self.voice.system_prompt
    @property
    def personality(self) -> str:
        return self.voice.personality
    @property
    def negative_semantics(self) -> list[str]:
        return self.voice.negative_semantics
    @property
    def voice_version_hash(self) -> str | None:
        return self.voice.voice_version_hash
    # … voice_version_seq, voice_version_label, plus profile/posting accessors …
```

### c. AFTER — `app/models/account.py`

```python
"""Account document shape stored in RavenDB (collection Accounts).

The account's writing identity lives in `soul` (see AccountSoul). Older documents
stored a flat layout or a `voice` object; `_lift_legacy_fields` migrates both into `soul`.
"""

from typing import Literal  # NEW: correlation enum for ContrastPattern

from pydantic import AliasChoices, BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Soul defaults
# ─────────────────────────────────────────────────────────────────────────────

def default_system_prompt(niche: str) -> str:
    """Default *posting* prompt (structural composition instructions) for a niche.
    Name kept for compatibility with existing imports; it now seeds soul.posting_prompt."""
    return (
        f"Generate a post about {niche}. "
        "Open with a shocked, opinionated hook (conversational, not newsy) and keep it as one long, "
        "almost run-on sentence with commas—not a chain of short separate sentences. "
        "Post length: 150-280 characters."
    )


def default_contrast_patterns() -> list[dict]:
    """Default contrast patterns. These REPLACE the old negative_semantics list:
    each former 'avoid this' string becomes a pattern with correlation='negative'.
    Stored as plain dicts so Pydantic builds ContrastPattern instances on validation."""
    negatives = [
        "\"It's not that, it's this\" / \"It's not X, it's Y\" false-dichotomy reframes",
        "Similar contrast gimmicks: \"The real story isn't … it's …\", \"This isn't about X, it's about Y\"",
        "Em dash (—) punctuation; use commas or periods instead",
        "\"Same X, same Y — two different things\" / \"same this, same that\" parallel contrast formulas",
        "Obviously AI stock phrases: \"Let's be clear\", \"Here's the thing\", \"Make no mistake\", \"At the end of the day\", \"In today's world\"",
        "Stiff, press-release, or essay voice — write like a person talking, not a bot",
        "AP-style perfect grammar and Title Case on every name — use loose, live X caps instead",
        "Rhetorical question chains or faux-Socratic setup (\"The question isn't … it's …\")",
        "Numbered lesson lists, thread voice, or \"Lesson:\" / \"Thread:\" openers",
    ]
    return [{"text": t, "correlation": "negative"} for t in negatives]


def default_punctuation_rules() -> list[dict]:
    """Deterministic punctuation auto-fixes applied AFTER generation.
    Pure formatting hygiene only — NOT the old ~80 banned phrases (those are archived
    in docs/voice-banned-phrases-archive.md and intentionally not recreated here).
    `replacement: None` means 'delete the match'."""
    return [
        {"pattern": r"\s*[—–]\s*", "replacement": ", "},          # em/en dash → comma
        {"pattern": r"(?<=\w)\s*--\s*(?=\w)", "replacement": ", "},# double hyphen between words → comma
        {"pattern": r" {2,}", "replacement": " "},                  # collapse runs of spaces
        {"pattern": r"\s+([,.!?;:])", "replacement": r"\1"},       # drop space before punctuation
        {"pattern": r",\s*,", "replacement": ","},                  # ",," → ","
        {"pattern": r"\.\s*\.", "replacement": "."},               # ".." → "."
        {"pattern": r",\s*\.", "replacement": "."},                # ",." → "."
        {"pattern": r"^[,;:\s]+", "replacement": ""},              # strip leading punctuation/space
    ]


def format_contrast_patterns_for_prompt(patterns: list["ContrastPattern"] | list[dict] | None) -> str:
    """Render contrast patterns into a compose-prompt block, split by correlation.
    Negative → things to avoid; positive → things to lean into. Replaces
    format_negative_semantics_for_prompt(). Accepts model instances or raw dicts."""
    def _text(p) -> str:
        return (p.text if isinstance(p, ContrastPattern) else str(p.get("text", ""))).strip()
    def _corr(p) -> str:
        return p.correlation if isinstance(p, ContrastPattern) else str(p.get("correlation", "negative"))

    items = [p for p in (patterns or []) if _text(p)]
    if not items:
        items = [ContrastPattern.model_validate(d) for d in default_contrast_patterns()]

    avoid = [_text(p) for p in items if _corr(p) == "negative"]
    lean = [_text(p) for p in items if _corr(p) == "positive"]

    blocks: list[str] = []
    if avoid:
        blocks.append("Avoid these patterns and tells:\n" + "\n".join(f"- {t}" for t in avoid))
    if lean:
        blocks.append("Lean into these patterns:\n" + "\n".join(f"- {t}" for t in lean))
    return "\n\n".join(blocks)


# ─────────────────────────────────────────────────────────────────────────────
# Soul building blocks
# ─────────────────────────────────────────────────────────────────────────────

class ContrastPattern(BaseModel):
    """A writing pattern the LLM should avoid or favor.
    correlation drives how it is rendered into the prompt (see format_contrast_patterns_for_prompt)."""
    text: str
    correlation: Literal["positive", "negative"] = "negative"


class PunctuationRule(BaseModel):
    """A deterministic regex auto-fix applied to generated text.
    replacement=None deletes the match; otherwise substitutes."""
    pattern: str
    replacement: str | None = None


class AccountSoul(BaseModel):
    """The writing identity of an account: who it is and how its text is shaped."""
    # Prose describing character, likes/dislikes, reactions to people/topics, tone quirks
    # (e.g. occasional lowercase sentence starts). This is the primary LLM steering text.
    personality: str = Field(default="")
    # Structural instructions for composing a post (was AccountVoice.system_prompt).
    posting_prompt: str = Field(default="")
    # LLM guidance: avoid (negative) / lean into (positive). Replaces negative_semantics.
    contrast_patterns: list[ContrastPattern] = Field(default_factory=default_contrast_patterns)
    # Deterministic post-generation punctuation hygiene (auto-fix; never regenerate).
    punctuation_rules: list[PunctuationRule] = Field(default_factory=default_punctuation_rules)
    # Version stamp; bumps when ANY field above changes (see voice_version_service).
    voice_version_hash: str | None = None
    voice_version_seq: int = 1
    voice_version_label: str | None = "v1"


def default_soul(niche: str) -> AccountSoul:
    """Fresh soul for a new account; posting_prompt is seeded from the niche."""
    return AccountSoul(
        personality="",
        posting_prompt=default_system_prompt(niche),
        contrast_patterns=[ContrastPattern.model_validate(d) for d in default_contrast_patterns()],
        punctuation_rules=[PunctuationRule.model_validate(d) for d in default_punctuation_rules()],
    )


class AccountProfile(BaseModel):
    niche: str
    # … UNCHANGED …


class AccountPostingState(BaseModel):
    # … UNCHANGED …


class AccountDocument(BaseModel):
    """Full account row in RavenDB. Document id: accounts/{account_id}."""

    account_id: str
    profile: AccountProfile
    # NEW: soul replaces the old `voice` object as the single writing-identity source.
    soul: AccountSoul = Field(default_factory=AccountSoul)
    posting: AccountPostingState = Field(default_factory=AccountPostingState)

    @model_validator(mode="before")
    @classmethod
    def _lift_legacy_fields(cls, value: object) -> object:
        """Accept three shapes and normalize to {account_id, profile, soul, posting}:
          (A) already-nested NEW docs (have 'soul')         → pass through
          (B) nested docs with legacy 'voice' but no 'soul' → migrate voice → soul
          (C) old flat docs (no 'profile')                  → lift everything into groups
        """
        if not isinstance(value, dict):
            return value

        # (A)/(B): already nested (has 'profile')
        if "profile" in value:
            if "soul" not in value or not value.get("soul"):
                legacy_voice = value.get("voice") or {}
                value["soul"] = _soul_from_legacy(legacy_voice)
            value.pop("voice", None)  # drop deprecated object; soul is canonical
            return value

        # (C): old flat document — lift profile/soul/posting out of top-level keys
        return {
            "account_id": value.get("account_id"),
            "profile": {
                "niche": value.get("niche") or value.get("account_id") or "",
                "twitter_handle": value.get("twitter_handle") or "",
                "status": value.get("status") or "active",
                "followers": value.get("followers") or 0,
                "posts_total": value.get("posts_total") or 0,
                "registered_at": value.get("registered_at"),
                "followers_when_registered": value.get("followers_when_registered"),
                "search_queries": list(value.get("search_queries") or []),
            },
            "soul": _soul_from_legacy(value),  # reads system_prompt/personality/negative_semantics if present
            "posting": {
                "last_interval_slot": value.get("last_interval_slot") or value.get("last_post_slot"),
                "last_post_id": value.get("last_post_id"),
                "last_post_text": value.get("last_post_text"),
                "last_post_at": value.get("last_post_at"),
                "last_post_views": value.get("last_post_views"),
                "copied_reference_tweet_ids": value.get("copied_reference_tweet_ids") or [],
            },
        }

    # ── Backward-compat accessors (kept to shield existing call sites; now back soul) ──
    @property
    def system_prompt(self) -> str:
        return self.soul.posting_prompt
    @system_prompt.setter
    def system_prompt(self, v: str) -> None:
        self.soul.posting_prompt = v

    @property
    def posting_prompt(self) -> str:        # NEW canonical accessor
        return self.soul.posting_prompt
    @posting_prompt.setter
    def posting_prompt(self, v: str) -> None:
        self.soul.posting_prompt = v

    @property
    def personality(self) -> str:
        return self.soul.personality
    @personality.setter
    def personality(self, v: str) -> None:
        self.soul.personality = v

    @property
    def contrast_patterns(self) -> list[ContrastPattern]:   # NEW
        return self.soul.contrast_patterns
    @contrast_patterns.setter
    def contrast_patterns(self, v: list[ContrastPattern]) -> None:
        self.soul.contrast_patterns = v

    @property
    def punctuation_rules(self) -> list[PunctuationRule]:    # NEW
        return self.soul.punctuation_rules
    @punctuation_rules.setter
    def punctuation_rules(self, v: list[PunctuationRule]) -> None:
        self.soul.punctuation_rules = v

    @property
    def voice_version_hash(self) -> str | None:
        return self.soul.voice_version_hash
    @voice_version_hash.setter
    def voice_version_hash(self, v: str | None) -> None:
        self.soul.voice_version_hash = v

    @property
    def voice_version_seq(self) -> int:
        return self.soul.voice_version_seq
    @voice_version_seq.setter
    def voice_version_seq(self, v: int) -> None:
        self.soul.voice_version_seq = v

    @property
    def voice_version_label(self) -> str | None:
        return self.soul.voice_version_label
    @voice_version_label.setter
    def voice_version_label(self, v: str | None) -> None:
        self.soul.voice_version_label = v

    # NOTE: the `negative_semantics` accessor is INTENTIONALLY REMOVED.
    #       EVERY reader must be updated in its own task (the original "etc." hid two
    #       live readers that broke at runtime). The complete sweep:
    #         - runner.py compose_formatted_post call (~line 331)  → Task 06 (contrast_patterns)
    #         - runner.py TickInput construction      (~line 295)  → Task 06 (drop the arg)
    #         - account_snapshot_service.py:74 (live /snapshot route) → Task 02 addendum (soul fields)
    #         - voice_version_service.py revision write              → Task 05
    #         - account_update_service / account_repository (dict, not accessor) → Tasks 03 / 04
    #       Confirm completeness with: grep -rn "\.negative_semantics" backend/app backend/scripts.

    # … all profile/posting accessors (niche, twitter_handle, followers, last_post_*, …) UNCHANGED …

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"accounts/{account_id}"


def _soul_from_legacy(src: dict) -> dict:
    """Build a soul dict from a legacy flat doc or legacy `voice` object.
    - posting_prompt ← system_prompt
    - personality    ← personality
    - contrast_patterns ← negative_semantics mapped to correlation='negative'
      (falls back to defaults when absent)
    - punctuation_rules ← defaults (legacy docs never had these)
    Version stamp is carried over so we don't reset history on migration."""
    neg = src.get("negative_semantics")
    contrast = (
        [{"text": s, "correlation": "negative"} for s in neg if s and str(s).strip()]
        if neg else default_contrast_patterns()
    )
    return {
        "personality": src.get("personality") or "",
        "posting_prompt": src.get("system_prompt") or src.get("posting_prompt") or "",
        "contrast_patterns": contrast,
        "punctuation_rules": src.get("punctuation_rules") or default_punctuation_rules(),
        "voice_version_hash": src.get("voice_version_hash"),
        "voice_version_seq": int(src.get("voice_version_seq") or 1),
        "voice_version_label": src.get("voice_version_label") or "v1",
    }
```

### d. Written explanation

The model file becomes the contract for the whole feature. `AccountSoul` groups the four writing controllers plus the version stamp. The two helper models give us validation (e.g. a bad `correlation` value is rejected at the boundary) and clean JSON for the API/frontend.

`_lift_legacy_fields` is the migration linchpin. RavenDB documents are schemaless, so the validator must absorb three historical shapes and always emit `{account_id, profile, soul, posting}`. The shared `_soul_from_legacy` helper does the field mapping in one place — crucially translating `negative_semantics → contrast_patterns(negative)`. Because the validator drops the `voice` key, the first `save()` of the existing `JohnJames_News` document rewrites it in canonical form (see Task 04 for the serializer that must stop emitting `voice`).

The accessors are retained as a thin shim so we don't have to touch every `account.system_prompt`/`account.personality` reader in this task. The one accessor we *remove* is `negative_semantics`, by design — it forces the (few) real call sites to be updated to `contrast_patterns`, which Tasks 03/04/06 handle explicitly.

---

## Decision Defense

**Why remove `AccountVoice` instead of keeping it for compatibility?**
With a single production account, the cost of a permanent dual-write/dual-read is higher than a one-time migration. Keeping `voice` would mean every future reader has to know which of two fields is authoritative — exactly the ambiguity we're trying to kill. The validator + serializer migrate the lone document transparently on first save.

**Why keep the property accessors but drop only `negative_semantics`?**
The accessors are a cheap compatibility layer that avoids a large, mechanical, error-prone sweep of `runner.py`/services in this task. But `negative_semantics` has no 1:1 successor (it folds into a *typed, correlated* structure), so silently aliasing it would hide a semantic change. Removing it surfaces the call sites and forces a correct migration to `contrast_patterns`.

> **Lower-risk alternative (if you cannot confidently enumerate every reader):** keep a *read-only* `negative_semantics` property that derives the negative-correlation texts from `contrast_patterns` (`return [p.text for p in self.soul.contrast_patterns if p.correlation == "negative"]`, no setter). This shields any reader the grep missed at the cost of keeping the term alive. The recommended path is still to fix the (now fully enumerated) call sites above; reach for the shim only if a `grep -rn "\.negative_semantics"` turns up callers you can't safely touch in this change.

**Why store defaults as `list[dict]` in the factory functions, then validate into models?**
Pydantic `default_factory` must return plain data; returning model instances risks shared-mutable-default bugs and complicates JSON dumping. Returning dicts and letting field validation coerce them into `ContrastPattern`/`PunctuationRule` is the idiomatic, safe pattern and keeps the factories reusable by the migration helper and the API layer.

**Why does `format_contrast_patterns_for_prompt` split by correlation rather than dumping one list?**
The positive/negative enum is only meaningful if it changes behavior. Rendering negatives under "avoid" and positives under "lean into" gives the LLM directional guidance and makes the field worth having. A flat dump would make `correlation` decorative.

**No frontend in this task.** UI interaction steps are documented in `08-frontend.md`.

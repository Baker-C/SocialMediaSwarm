# Task 06 — Compose Pipeline (the behavioral core)

## Task Overview

This is where the soul stops being stored data and starts shaping posts. Files:

| File | Change |
|---|---|
| `app/interval/orchestration/voice_polish.py` | Rewrite: pure, parameterized, **punctuation-only** auto-fix. Delete banned-phrases/soft-flag/casual-lowercase machinery. |
| `app/interval/compose_timeline_post.py` | Inject `contrast_patterns` into the prompt; run punctuation polish on opinion+quip **before** the length-budget check. |
| `app/pipeline/tools/llm/compose_timeline_post.py` | Update tool signature (`negative_semantics` → `contrast_patterns`/`punctuation_rules`). |
| `app/interval/runner.py` | Update **both** the `compose_formatted_post(...)` call site (~line 326) AND the `TickInput(...)` construction (~line 288) — the latter still reads the deleted `account.negative_semantics` accessor. |
| `app/interval/schemas.py` | Drop the `negative_semantics` (and dead `account_system_prompt`) fields from `TickInput`. |
| `app/interval/orchestration/__init__.py` | Update exports (drop deleted symbols). |
| `app/interval/orchestration/voice_select.py` | **Delete** (dead alternate path). |
| `app/interval/orchestration/safety_filter.py` | Remove polish coupling (or delete if unused elsewhere). |
| `app/api/routes/analytics.py` | Delete the `/voice-polish-rules` endpoint. |
| `app/services/voice_polish_rules.py` | **Delete** (rules are per-account now). |
| tests | Update `test_voice_polish.py`; delete `test_voice_select.py`; drop assertions on removed exports. |

**What it affects:** the live post-generation path (`runner.py` → `compose_formatted_post` → guardian) and the dead alternate path (`voice_select`/`safety_filter`). After this task, punctuation auto-fix is actually applied in production and contrast patterns actually steer the LLM.

**Decisions (from `00-overview.md`):** punctuation = auto-fix only (no regen); contrast = LLM guidance only (no regex detection, no soft-flag); casual-lowercase becomes personality prose (deleted from code); the ~80 banned phrases are archived (Task 07), not reimplemented.

**Dependencies:** Tasks 01 (soul + `format_contrast_patterns_for_prompt`), 03 (so soul is editable).

---

## Proposed Solution

### Part A — `voice_polish.py` (rewrite)

#### BEFORE (≈287 lines): module-level regex globals + multi-purpose `polish_post`
```python
VOICE_SOFT_FLAG_PREFIX = "voice_soft_flag"
_BANNED_PHRASES = ( … ~80 (regex, replacement) pairs … )
_SOFT_FLAG_PATTERNS = ( … 22 named contrast regexes … )
_SOFT_FLAG_PHRASE_PATTERNS = ( … 13 phrase regexes … )
SENTENCE_START_LOWERCASE_PROBABILITY = 0.30

def apply_casual_sentence_starts(text, *, probability=..., rng=None): ...
def detect_voice_violations(text) -> list[str]: ...

def polish_post(text: str) -> VoicePolishResult:
    # apply _BANNED_PHRASES, em-dash/space cleanup,
    # detect_voice_violations → soft_flag, casual lowercasing …
```

#### AFTER — full file
```python
"""Deterministic punctuation polish applied after generation, before posting.

Pure & parameterized: callers pass the account's punctuation rules; there is no
module-level rule state. This module ONLY normalizes punctuation/whitespace.
Voice/persona steering (banned phrases, contrast tells, casual caps) is handled
at generation time via the soul's personality + contrast_patterns — not here.
(Historical banned-phrase list archived in docs/voice-banned-phrases-archive.md.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.account import PunctuationRule, default_punctuation_rules


@dataclass
class VoicePolishResult:
    original: str
    polished: str
    changed: bool
    notes: list[str] = field(default_factory=list)


def _coerce_rules(rules) -> list[dict]:
    """Accept list[PunctuationRule] | list[dict] | None → list[{pattern, replacement}].
    None/empty falls back to the shared defaults so a misconfigured account still
    gets basic hygiene (em-dash removal etc.)."""
    if not rules:
        return default_punctuation_rules()
    out: list[dict] = []
    for r in rules:
        if isinstance(r, PunctuationRule):
            out.append({"pattern": r.pattern, "replacement": r.replacement})
        elif isinstance(r, dict) and r.get("pattern"):
            out.append({"pattern": r["pattern"], "replacement": r.get("replacement")})
    return out or default_punctuation_rules()


def polish_text(text: str, rules=None) -> VoicePolishResult:
    """Apply punctuation auto-fixes to a single block of text (opinion or quip).
    Each rule: substitute `pattern`→`replacement`, or delete the match if replacement is None.
    Rules apply in order; later rules see earlier results (e.g. em-dash→', ' then collapse spaces)."""
    original = (text or "").strip()
    if not original:
        return VoicePolishResult(original="", polished="", changed=False)

    out = original
    notes: list[str] = []
    for rule in _coerce_rules(rules):
        repl = rule["replacement"]
        compiled = re.compile(rule["pattern"])
        new_out = compiled.sub("" if repl is None else repl, out)
        if new_out != out:
            notes.append(f"fix:{rule['pattern'][:40]}")
            out = new_out

    out = out.strip()
    return VoicePolishResult(original=original, polished=out, changed=out != original, notes=notes)


# Backwards-compatible name used by older imports; same behavior as polish_text.
def polish_post(text: str, rules=None) -> VoicePolishResult:
    return polish_text(text, rules)
```

**Deleted from this module:** `_BANNED_PHRASES`, `_SOFT_FLAG_PATTERNS`, `_SOFT_FLAG_PHRASE_PATTERNS`, `SENTENCE_START_LOWERCASE_PROBABILITY`, `VOICE_SOFT_FLAG_PREFIX`, `apply_casual_sentence_starts`, `detect_voice_violations`, `_lowercase_first_letter`, and the `violations`/`soft_flag` fields on `VoicePolishResult`.

### Part B — `app/interval/orchestration/__init__.py`
```python
# BEFORE
from app.interval.orchestration.safety_filter import select_from_ranked
from app.interval.orchestration.voice_polish import detect_voice_violations, polish_post
from app.interval.orchestration.voice_select import select_polished_from_ranked
__all__ = [ …, "polish_post", "select_polished_from_ranked", "select_from_ranked", "detect_voice_violations", … ]

# AFTER  (drop deleted symbols; keep polish_post/polish_text)
from app.interval.orchestration.voice_polish import polish_post, polish_text
__all__ = [ …, "polish_post", "polish_text", … ]   # remove select_*/detect_voice_violations
```

### Part C — delete dead alternate path
- **Delete** `app/interval/orchestration/voice_select.py` (only consumer was `safety_filter.select_from_ranked`).
- `app/interval/orchestration/safety_filter.py`: if `select_from_ranked` is referenced nowhere in `app/` (confirm with grep — current grep shows only its own definition + `__init__` export), **delete the file**. Otherwise, strip its `select_polished_from_ranked` call and inline a guardian-only selection.

### Part D — `compose_timeline_post.py` (integrate polish + contrast prompt)

#### BEFORE (key regions)
```python
from app.models.account import format_negative_semantics_for_prompt
# …
def _generate_post_parts(winner, niche, budget, *, account_system_prompt="", account_personality="",
                         negative_semantics=None, reference_context_block="", regeneration_round,
                         length_attempt, previous, safety_reject_reason=None):
    # …
    user = prompt_loader.load_template(
        "tasks/compose_timeline_post.user.md",
        niche=…, account_system_prompt=structure, account_personality=_personality_section(account_personality),
        negative_semantics_block=format_negative_semantics_for_prompt(negative_semantics),
        reference_context_block=ref_block, …)
    # … returns (opinion, quip)

def compose_formatted_post(winner, niche, *, account_system_prompt="", account_personality="",
                           negative_semantics=None, reference_context_block="",
                           regeneration_round=0, safety_reject_reason=None) -> str:
    # …
    for length_attempt in range(COMPOSE_LENGTH_MAX_ATTEMPTS):
        opinion, quip = _generate_post_parts(…, negative_semantics=negative_semantics, …)
        if fits_post_budget(opinion, quip, budget):
            body = assemble_formatted_body(opinion, quip, source_url)
            return body
        previous = (opinion, quip)
    opinion, quip = _shrink_to_budget(opinion, quip, budget)
    return assemble_formatted_body(opinion, quip, source_url)
```

#### AFTER (key regions, with inline rationale)
```python
from app.models.account import format_contrast_patterns_for_prompt   # was format_negative_semantics_for_prompt
from app.interval.orchestration.voice_polish import polish_text       # NEW

def _generate_post_parts(winner, niche, budget, *, account_posting_prompt="", account_personality="",
                         contrast_patterns=None, reference_context_block="", regeneration_round,
                         length_attempt, previous, safety_reject_reason=None):
    # … claude/fallback unchanged …
    structure = (account_posting_prompt or "").strip() or ("Energetic, emotional opinion … loose X grammar …")
    user = prompt_loader.load_template(
        "tasks/compose_timeline_post.user.md",
        niche=(niche or "general").strip(),
        account_system_prompt=structure,                # template var name kept (Task 07 renames file vars)
        account_personality=_personality_section(account_personality),
        # CHANGED: contrast patterns rendered as avoid/lean blocks (replaces negative_semantics_block)
        negative_semantics_block=format_contrast_patterns_for_prompt(contrast_patterns),
        reference_context_block=ref_block, …)
    # … returns (opinion, quip)

def compose_formatted_post(winner, niche, *, account_posting_prompt="", account_personality="",
                           contrast_patterns=None, punctuation_rules=None,   # CHANGED params
                           reference_context_block="", regeneration_round=0,
                           safety_reject_reason=None) -> str:
    source_row = {**winner.metrics, "id": winner.tweet_id, "tweet_id": winner.tweet_id}
    source_url = select_chosen_post_media_url(source_row) or ""
    budget = compute_post_length_budget(source_url)
    opinion, quip = _fallback_compose(winner, niche, budget)
    previous = None

    for length_attempt in range(COMPOSE_LENGTH_MAX_ATTEMPTS):
        opinion, quip = _generate_post_parts(
            winner, niche, budget,
            account_posting_prompt=account_posting_prompt,
            account_personality=account_personality,
            contrast_patterns=contrast_patterns,         # CHANGED
            reference_context_block=reference_context_block,
            regeneration_round=regeneration_round,
            length_attempt=length_attempt, previous=previous,
            safety_reject_reason=safety_reject_reason,
        )
        # NEW: punctuation auto-fix BEFORE the budget check, so fixes that change
        # length (em-dash → ", ", removals) can't push the assembled post over 280.
        opinion = polish_text(opinion, punctuation_rules).polished
        quip = polish_text(quip, punctuation_rules).polished

        if fits_post_budget(opinion, quip, budget):
            body = assemble_formatted_body(opinion, quip, source_url)
            logger.info("compose ok tweet_id=%s len=%s attempt=%s", winner.tweet_id, len(body), length_attempt)
            return body
        previous = (opinion, quip)

    # Emergency path: POLISH FIRST, THEN SHRINK — shrink must be the last length-changing
    # step so the budget guarantee actually holds. (Corrected from the first draft, which
    # shrank then polished; the em-dash→", " rule GROWS length, so polishing after shrink
    # could push the post back over 280 with no re-check.) By this point the loop already
    # ran punctuation polish on these strings, so this call is normally a no-op; shrink
    # then trims to budget and is purely length-reducing.
    opinion = polish_text(opinion, punctuation_rules).polished
    quip = polish_text(quip, punctuation_rules).polished
    opinion, quip = _shrink_to_budget(opinion, quip, budget)
    return assemble_formatted_body(opinion, quip, source_url)
```

> Polishing **opinion and quip separately** (not the assembled body) guarantees the appended media URL is never mangled by a punctuation rule. Ordering polish **before** the final `_shrink_to_budget` guarantees no auto-fix can re-inflate the post past the budget after the last length check.

### Part E — `app/pipeline/tools/llm/compose_timeline_post.py`
```python
# Update run(...) signature + forwarded kwargs:
def run(ctx, *, winner, niche,
        account_posting_prompt="", account_personality="",
        contrast_patterns=None, punctuation_rules=None,     # was account_system_prompt/negative_semantics
        reference_context_block="", regeneration_round=0, safety_reject_reason=None) -> StepResult:
    body = compose_formatted_post(
        winner, niche,
        account_posting_prompt=account_posting_prompt,
        account_personality=account_personality,
        contrast_patterns=contrast_patterns,
        punctuation_rules=punctuation_rules,
        reference_context_block=reference_context_block,
        regeneration_round=regeneration_round,
        safety_reject_reason=safety_reject_reason,
    )
    ctx.set("composed_body", body)
    return StepResult(ok=True, payload={"body": body})
```

### Part F — `app/interval/runner.py` (call site ~line 326)
```python
# BEFORE
body = compose_formatted_post(
    winner, account.niche,
    account_system_prompt=(account.system_prompt or "").strip(),
    account_personality=(account.personality or "").strip(),
    negative_semantics=list(account.negative_semantics or []),
    reference_context_block=reference_context_block,
    regeneration_round=reg_round,
    safety_reject_reason=candidate_reject if reg_round > 0 else None,
)

# AFTER
body = compose_formatted_post(
    winner, account.niche,
    account_posting_prompt=(account.posting_prompt or "").strip(),   # accessor → soul.posting_prompt
    account_personality=(account.personality or "").strip(),
    contrast_patterns=list(account.contrast_patterns or []),          # soul.contrast_patterns
    punctuation_rules=list(account.punctuation_rules or []),          # soul.punctuation_rules
    reference_context_block=reference_context_block,
    regeneration_round=reg_round,
    safety_reject_reason=candidate_reject if reg_round > 0 else None,
)
```

#### Part F.2 — `runner.py` `TickInput` construction (~line 288) — **the call site the first draft missed**
`runner.py` builds a `TickInput` *above* the compose loop, and it reads `account.negative_semantics` — the accessor Task 01 deletes. This line executes on every tick, so without this edit the runner raises `AttributeError` before composing anything. `tick_input` is only consumed by `trace_step` (the `interval_crew` path it was designed for is not invoked here — see Part F.3), so the simplest correct fix is to drop the voice fields.
```python
# BEFORE
tick_input = TickInput(
    account_id=account.account_id,
    niche=account.niche,
    slot=ctx.slot,
    mode=ctx.mode,
    account_system_prompt=(account.system_prompt or "").strip(),
    account_personality=(account.personality or "").strip(),
    negative_semantics=list(account.negative_semantics or []),   # ← deleted accessor → AttributeError
    max_candidates=ctx.max_candidates,
)

# AFTER  (TickInput is trace metadata only; voice now flows directly into compose_formatted_post)
tick_input = TickInput(
    account_id=account.account_id,
    niche=account.niche,
    slot=ctx.slot,
    mode=ctx.mode,
    account_personality=(account.personality or "").strip(),
    max_candidates=ctx.max_candidates,
)
```

#### Part F.3 — `app/interval/schemas.py` (`TickInput` model) + the dead `interval_crew` path
Drop the now-unused voice fields from the `TickInput` contract so the model matches the construction above:
```python
# BEFORE
class TickInput(BaseModel):
    account_id: str
    niche: str
    slot: str
    mode: TickMode = "scheduled"
    account_system_prompt: str = ""
    account_personality: str = ""
    negative_semantics: list[str] = Field(default_factory=list)
    max_candidates: int = 5

# AFTER
class TickInput(BaseModel):
    account_id: str
    niche: str
    slot: str
    mode: TickMode = "scheduled"
    account_personality: str = ""   # kept: still useful trace context
    max_candidates: int = 5
```
> **Confirm before deleting `account_system_prompt`:** grep for live consumers of the `interval_crew` runner (`app/interval_crew/runner.py`, `llm_pipeline.py`, `generate_candidates_task.py`). Current evidence is that `app/interval/runner.py` only passes `tick_input` to `trace_step`, so `interval_crew/` is a dead alternate path. If grep confirms no live caller, add a one-line header comment marking `app/interval_crew/` as legacy/slated for removal and proceed. If something *does* consume it live, keep `account_system_prompt` on `TickInput`, set it from `account.posting_prompt`, and feed `contrast_patterns` through that path too — don't leave it on the old vocabulary.

### Part G — delete the stopgap global-rules endpoint
- `app/api/routes/analytics.py`: remove the `get_voice_polish_rules` import and the `@router.get("/voice-polish-rules")` handler.
- **Delete** `app/services/voice_polish_rules.py`.
- Frontend hook `useVoicePolishRules.ts` and its usage are removed in Task 08.

### Tests
- `tests/test_voice_polish.py`: rewrite around `polish_text(text, rules)` — assert em-dash→comma, multi-space collapse, leading-punct strip, `replacement=None` deletes. Remove soft-flag/casual-lowercase tests.
- `tests/test_voice_select.py`: **delete** (module removed).
- Any test importing `detect_voice_violations`/`apply_casual_sentence_starts`/`select_*`: remove or port.
- `tests/unit/test_compose_timeline_post.py`: update kwargs (`account_posting_prompt`, `contrast_patterns`, `punctuation_rules`); add a case asserting an em-dash in the model output is gone from the final body.
- **`tests/unit/test_negative_semantics.py` (the first draft missed this entire file): rewrite as `tests/unit/test_contrast_patterns.py`.** It currently imports the removed `default_negative_semantics`/`format_negative_semantics_for_prompt`, passes the removed `account_system_prompt`/`negative_semantics` kwargs to `compose_formatted_post`, asserts the removed `acc.negative_semantics` accessor, and asserts the literal label `"Banned semantics"` in the prompt. New version:
  ```python
  from app.models.account import (
      AccountDocument, default_contrast_patterns, format_contrast_patterns_for_prompt,
  )

  def test_default_contrast_patterns_are_negative_by_default():
      pats = default_contrast_patterns()
      assert pats and all(p["correlation"] == "negative" for p in pats)

  def test_format_contrast_patterns_splits_avoid_and_lean():
      block = format_contrast_patterns_for_prompt([
          {"text": "hedge words", "correlation": "negative"},
          {"text": "punchy openers", "correlation": "positive"},
      ])
      assert "Avoid these patterns" in block and "hedge words" in block
      assert "Lean into these patterns" in block and "punchy openers" in block

  def test_document_to_account_backfills_contrast_patterns():
      acc = document_to_account({"account_id": "x", "niche": "News"})
      assert len(acc.contrast_patterns) >= 3

  # compose test: pass contrast_patterns=/punctuation_rules=, assert the
  # avoid/lean guidance (not "Banned semantics") reaches the user prompt.
  ```
- Cross-task test fixes that must also be green for Task 09: `test_account_update_service.py` (Task 03), `test_analytics_api.py` (Task 02), `test_voice_version_service.py` (Task 05).

### Written explanation
The live path (`runner.py`) gets two real upgrades: (1) it now passes the account's contrast patterns into the prompt via `format_contrast_patterns_for_prompt`, giving the LLM explicit avoid/lean guidance derived from the soul; (2) it now runs deterministic punctuation polish on the generated opinion/quip. Polishing *before* the budget check is the subtle-but-important ordering fix — auto-fixes change string length, so doing them after a "fits budget" check could yield an over-limit post.

Removing `voice_select.py`/`safety_filter.py`/`voice_polish_rules.py` and the global endpoint deletes the misleading "rules" surface that was never in the live path. The result is a single, honest pipeline: soul → prompt → generate → punctuation auto-fix → guardian → post.

---

## Decision Defense

**Why no regex detection of contrast patterns (and thus no soft-flag regeneration)?**
The user chose LLM guidance for contrast patterns. The old regex soft-flag system was (a) dead code not wired into `runner.py`, and (b) brittle — it matched surface forms and missed paraphrases. Steering the LLM with explicit avoid/lean lists addresses the root cause (generation) rather than patching symptoms (post-hoc detection). If output quality regresses, a future task can add optional regex guards — but we don't pay that complexity now.

**Why keep `polish_post` as an alias of `polish_text`?**
Minimizes churn for any external importer and the `__init__` export, while the clearer `polish_text(text, rules)` name communicates the per-block, parameterized contract. Both are pure functions of their inputs.

**Why polish per-block (opinion, quip) instead of the assembled body?**
The media URL is appended after composition. Running regex substitutions over a string that contains a URL risks corrupting it (e.g. a double-hyphen or punctuation rule hitting the URL). Per-block polishing keeps the URL untouched and keeps length accounting precise.

**Why delete `voice_polish_rules.py` and `/voice-polish-rules` rather than repoint them at the account?**
They modeled rules as *global*. The whole feature makes rules *per-account* and already exposes them via `/accounts/{id}/edit` (Task 03). Keeping a parallel global endpoint would be a second, conflicting source of truth.

**Why move casual-lowercasing out of code into personality prose?**
It's a stylistic trait of one persona, not a universal rule. Encoding it as personality text lets each account opt in/out naturally and lets the LLM apply it with judgment, instead of a blunt 30% coin-flip that could lowercase the wrong sentence.

---

## Frontend interaction (reference; see `08-frontend.md`)
No direct UI here, but to **verify** end-to-end: trigger a forced post (Posts page → run controls, or `scripts/docker-forced-post.ps1`), then open the Posts explorer / Latest Run panel and confirm the composed body contains no em-dashes and reflects contrast guidance. The Voice tab's "Punctuation Rules" list is the human-readable view of the rules applied here.

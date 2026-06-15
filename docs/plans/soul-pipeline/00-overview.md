# Soul Pipeline — Implementation Plan (Overview)

> **Status:** Ready to implement. Authored in a planning session; pick up cold from this folder.
> **Scope:** Backend (models, services, repository, compose pipeline, prompts) + Frontend (Voice tab) + Docs.
> **Target project:** `SocialMediaAutonomousAgents/` (backend = FastAPI + RavenDB, frontend = CRA/React).
> **DB reality:** Exactly **one** account exists today — `JohnJames_News`. A clean migration is low-risk; we are NOT carrying deprecated baggage forward.

---

## 1. Why this change

Today, the text that defines how an account writes a post is spread across **two very different places**:

| Controller | Where it lives now | Per-account? | Problem |
|---|---|---|---|
| `system_prompt` | `account.voice.system_prompt` (RavenDB) | ✅ | Name is ambiguous ("system" vs "posting") |
| `personality` | `account.voice.personality` (RavenDB) | ✅ | Fine |
| `negative_semantics` | `account.voice.negative_semantics` (RavenDB) | ✅ | Conceptually overlaps with contrast patterns |
| `_BANNED_PHRASES` (~80) | hardcoded in `voice_polish.py` | ❌ global | Not editable, not versioned, regex soup |
| `_SOFT_FLAG_PATTERNS` (~22) | hardcoded in `voice_polish.py` | ❌ global | Not editable, fragile, not in live flow |
| casual-lowercase 30% | hardcoded constant | ❌ global | Should be a personality trait, not a global rule |

The polish machinery (`voice_polish.py` → `voice_select.py` → `safety_filter.py`) is **not even wired into the live compose path** (`runner.py` → `compose_formatted_post`). It is dead/alternate code. So the "rules" the dashboard shows are not the rules actually shaping posts.

**Goal:** Consolidate everything that shapes post *text* into one cohesive, per-account, versioned object — the account **Soul** — and make the live pipeline actually use it.

## 2. The Soul model (target state)

```
account
└── soul
    ├── personality          # prose. Character, tone, what they like/dislike, how
    │                         # they react to people/topics. Tone quirks (e.g. "lowercases
    │                         # sentence starts now and then") live HERE as prose, not as a global rule.
    ├── posting_prompt        # was "system_prompt". Structural instructions for composing a post.
    ├── contrast_patterns     # list[{ text, correlation: positive|negative }]
    │                         # LLM guidance. Replaces negative_semantics. Negative = avoid,
    │                         # positive = lean into. Fed into the compose prompt.
    ├── punctuation_rules     # list[{ pattern (regex), replacement|null }]
    │                         # Deterministic post-generation AUTO-FIX (never regenerate).
    └── voice_version_{hash,seq,label}   # version stamp; bumps when ANY soul field changes
```

### How each piece flows through the pipeline

```
            ┌──────────────────────── account.soul ────────────────────────┐
            │ personality   posting_prompt   contrast_patterns   punctuation_rules
            └───────┬───────────┬───────────────────┬───────────────────┬───┘
                    │           │                   │                   │
        ┌───────────▼───────────▼───────────────────▼─────┐             │
        │ 1. COMPOSE PROMPT (LLM input)                    │             │
        │    personality + posting_prompt +                │             │
        │    contrast_patterns (neg → "avoid", pos → "lean")│            │
        └───────────────────────┬──────────────────────────┘            │
                                 │ LLM generates opinion + quip          │
                    ┌────────────▼───────────────────────────┐          │
                    │ 2. PUNCTUATION AUTO-FIX (deterministic) │◄─────────┘
                    │    apply regex rules to opinion & quip   │
                    │    (em-dash→comma, collapse spaces, …)   │
                    └────────────┬─────────────────────────────┘
                                 │ assemble (opinion + quip + media URL), length check
                    ┌────────────▼─────────────┐
                    │ 3. SAFETY GUARDIAN        │  (unchanged; may regenerate)
                    └────────────┬─────────────┘
                                 │ approved
                    ┌────────────▼─────────────┐
                    │ 4. FINALIZE & POST        │
                    └───────────────────────────┘
```

**Key behavioral decisions (confirmed with the user):**
- **Punctuation rules = auto-fix only.** They never trigger regeneration.
- **Contrast patterns = LLM guidance only.** No fragile regex post-detection. The positive/negative correlation is rendered into the prompt. (This replaces the old soft-flag-regenerate mechanism, which was dead code anyway.)
- **The ~80 banned phrases are dropped from code** and archived to `SocialMediaAutonomousAgents/docs/voice-banned-phrases-archive.md`. They are intentionally NOT recreated as punctuation rules. The LLM is steered away from them via `personality` + `contrast_patterns` instead.
- **The 30% casual-lowercase behavior becomes prose in `personality`**, not a deterministic step.

## 3. Architecture improvements baked into this plan

This plan does more than relocate fields. The following were chosen deliberately (the user invited larger changes where they improve quality):

1. **Drop `AccountVoice` entirely; `soul` is the single source of truth.** With one account, a clean cutover beats permanently maintaining two parallel structures. The backward-compat *property accessors* on `AccountDocument` are kept (they shield ~dozens of call sites) but are re-pointed at `soul`. See `01-data-model.md`.
2. **Strong typing over `list[dict]`.** `ContrastPattern` and `PunctuationRule` are Pydantic models, validated on read/write, and surfaced as real TypeScript types on the frontend. See `01` and `08`.
3. **Contrast patterns get *meaning*.** The positive/negative enum is not decorative — it changes how each pattern is rendered into the prompt (`format_contrast_patterns_for_prompt`). See `06`.
4. **`polish_post` becomes pure & parameterized.** No module-level regex globals, no hidden state — `polish_post(text, rules)`. Trivially unit-testable. See `06`.
5. **Polish runs *before* the length budget check**, so auto-fixes (which change length) can't push a post over 280 chars. See `06`.
6. **Dead code removal.** `voice_select.py`, `safety_filter.py`'s polish coupling, `_SOFT_FLAG_PATTERNS`, `apply_casual_sentence_starts`, `detect_voice_violations`, and their tests are removed. See `06`.
7. **Defaults centralized.** One `default_soul(niche)` builder + per-field default factories; stop sprinkling `or default_…()` across the repository. See `01`/`04`.

### Deliberately deferred (documented, not done)
- **Renaming `voice_version_*` → `soul_version_*`.** Blast radius touches the revision repository, analytics `voiceComparison.ts`, and `AccountSummary`. Kept as-is to bound this change; see `05` "Decision Defense" for the rename recipe if desired later.
- **A dedicated soul-editing UI.** This plan makes the Voice tab *display* the full soul and keeps the existing PATCH-based edit form working. A bespoke editor (regex tester, pattern reordering) is future work.

## 4. File-by-file task index

| # | Plan file | Touches | Size |
|---|---|---|---|
| 1 | `01-data-model.md` | `app/models/account.py` | Large |
| 2 | `02-voice-revision.md` | `app/models/voice_revision.py` | Small |
| 3 | `03-services-and-api.md` | `account_update_service.py`, `account_create_service.py` | Medium |
| 4 | `04-repository-and-migration.md` | `account_repository.py` + migration script | Medium |
| 5 | `05-versioning.md` | `voice_version_service.py` | Small |
| 6 | `06-compose-pipeline.md` | `voice_polish.py`, `compose_timeline_post.py`, `runner.py`, dead-code removal | Large |
| 7 | `07-prompts-and-archive.md` | `compose_timeline_post.user.md`/`.system.md`, banned-phrases archive doc | Medium |
| 8 | `08-frontend.md` | `types/domain/*`, `VoiceExperimentsPage.tsx`, endpoints | Medium |
| 9 | `09-verification.md` | build, docker, end-to-end checks, rollback | — |

> **Files the original index missed (added in post-review corrections, see §7):**
> `app/models/account_snapshot.py` + `app/services/account_snapshot_service.py` (Task 02 addendum),
> `app/interval/schemas.py` `TickInput` and the `runner.py` `TickInput` construction (Task 06),
> `frontend/src/components/UpdateAccountModal.tsx` (Task 08), and the test files
> `test_negative_semantics.py` / `test_account_update_service.py` / `test_analytics_api.py` /
> `test_voice_version_service.py` (handled in their owning tasks).

## 5. Recommended implementation order

`01 → 02 → 05 → 04 → 03 → 07 → 06 → 08 → 09`

Rationale: models first (everything imports them); versioning + repository next (so save/load round-trips a soul); services/API so the document can be edited; prompts + compose so the soul actually drives generation; frontend last; verification throughout.

> **Correction (post-review):** the earlier claim that *each step compiles independently* is **wrong**. Task 01 deletes `AccountVoice`, `default_negative_semantics`, and `format_negative_semantics_for_prompt`, which several modules still import — so the tree is import-broken from Task 01 until its consumers are updated. Implement `01 → 02 → 04` plus the full call-site sweep (now including `account_snapshot_service.py` and the `runner.py` `TickInput` construction) back-to-back, and expect a green `pytest` only after Task 06. Do not run `py_compile`/`pytest` mid-sequence and conclude a failure means you broke something.

## 6. Global definition of done

- `python -m py_compile` clean across touched backend files; `pytest` green (updated/removed voice tests).
- `npm run build` clean (no new TS errors).
- `docker compose up -d --build` healthy.
- `GET /api/accounts/JohnJames_News/edit` returns a fully-populated `soul`.
- A freshly composed post shows punctuation auto-fix applied (no em-dashes) and contrast guidance honored.
- Voice tab renders personality, posting prompt, contrast patterns (color-coded), punctuation rules.
- `account.voice` no longer written to new documents; legacy `voice` on the existing doc migrated to `soul` on first save.

## 7. Post-review corrections (gaps found after the plan was first written)

A review against the live code surfaced ten gaps. Each is now folded into the owning task; this table is the index.

| # | Gap | Fix (summary) | Lives in |
|---|---|---|---|
| 1 | Removed `negative_semantics` accessor still read by `account_snapshot_service.py:74` (live route) and the `runner.py` `TickInput` construction — neither was in any task. | Snapshot stores the soul fields (mirrors the revision); `runner.py` `TickInput` drops the voice args. | `01` (sweep note), `02` (snapshot addendum), `06` (runner/schemas) |
| 2 | The real edit UI is `UpdateAccountModal.tsx`, not a "settings form". It reads/sends `system_prompt`, which Task 03 renames/ignores → editing the posting prompt silently no-ops; personality/contrast/punctuation have no editor at all. | Modal reads `posting_prompt` (with `system_prompt` fallback) and PATCHes `posting_prompt`; add a personality textarea; defer the list editors and verify them via the existing `curl` PATCH. | `08`, `09` |
| 3 | Four breaking test files were unlisted (`test_negative_semantics`, `test_account_update_service`, `test_analytics_api`, `test_voice_version_service`). | Each rewritten in its owning task to the new vocabulary. | `02`, `03`, `05`, `06` |
| 4 | Task 09 grep guards flag legitimate retained-accessor use and skip `scripts/`+`tests/`. | Guard the deleted *structure* (`\.voice\.`, `AccountVoice`, `default_negative_semantics`) across `app/ scripts/ tests/`. | `09` |
| 5 | Task 02 (drop legacy columns + default-factory fill) contradicts Task 08 (graceful legacy display) → old revisions render fabricated default patterns. | Revision model defaults new lists to **empty** and keeps `system_prompt`/`negative_semantics` as read-only passthrough. | `02`, `08` |
| 6 | A parallel `interval_crew` compose path + `TickInput` still carry the old vocabulary; `tick_input` is trace-only/dead. | Strip voice fields from `TickInput`; mark `interval_crew/` legacy. | `06` |
| 7 | "Each step compiles independently" is false. | Corrected in §5 above. | `00` |
| 8 | Emergency `_shrink_to_budget` path polishes *after* shrink with no budget re-check → can exceed 280. | Reorder to polish-then-shrink; shrink is the last length-changing step. | `06` |
| 9 | `_normalize_patterns` docstring claims it sorts the list (it doesn't). | Doc fix: digest is order-sensitive by design. | `05` |
| 10 | Migration's first save always bumps the version (hash payload changed) — not noted. | Label the bump `manual_label="soul-migration"` and document the one-time bump. | `04`, `09` |

# Task 09 — Verification, Migration Run & Rollback

## Task Overview
End-to-end validation that the soul refactor works against the live stack (RavenDB + NATS + backend + frontend, all in Docker; the lone account is `JohnJames_News`). Covers: static checks, tests, migration execution, API checks, compose behavior, UI checks, and rollback.

**No production-code changes here** — this is the acceptance procedure. Run after Tasks 01–08.

---

## a. Static + unit checks (host)

```bash
# Backend syntax
cd SocialMediaAutonomousAgents/backend
python -m py_compile app/models/account.py app/models/voice_revision.py \
  app/services/account_repository.py app/services/account_update_service.py \
  app/services/account_create_service.py app/services/voice_version_service.py \
  app/interval/orchestration/voice_polish.py app/interval/compose_timeline_post.py \
  app/interval/runner.py app/pipeline/tools/llm/compose_timeline_post.py

# Backend tests (expect updated/removed voice tests to pass).
# The first draft under-listed these. All of the following were touched by the refactor
# and must be updated in their owning tasks (see each task's "Test fix" note):
#   test_voice_polish.py (06), test_voice_version_service.py (05),
#   test_compose_timeline_post.py (06), test_voice_revision_repository.py,
#   test_contrast_patterns.py (06; renamed from test_negative_semantics.py),
#   test_account_update_service.py (03), test_analytics_api.py (02).
# Sanity: test_negative_semantics.py and test_voice_select.py must be GONE.
test ! -f tests/unit/test_negative_semantics.py && echo "test_negative_semantics.py removed OK"
python -m pytest \
  tests/test_voice_polish.py tests/unit/test_voice_version_service.py \
  tests/unit/test_compose_timeline_post.py tests/test_voice_revision_repository.py \
  tests/unit/test_contrast_patterns.py tests/unit/test_account_update_service.py \
  tests/test_analytics_api.py -q
# Belt-and-suspenders: a full run catches any other importer of the deleted symbols.
python -m pytest -q

# Confirm dead modules are gone
test ! -f app/interval/orchestration/voice_select.py && echo "voice_select.py removed OK"
test ! -f app/services/voice_polish_rules.py && echo "voice_polish_rules.py removed OK"
```

```bash
# Frontend type-check + build
cd SocialMediaAutonomousAgents/frontend
npm run build      # must compile; no new TS errors
test ! -f src/hooks/queries/useVoicePolishRules.ts && echo "useVoicePolishRules.ts removed OK"
```

**Grep guards (should return nothing) — corrected from the first draft:**
```bash
cd SocialMediaAutonomousAgents
# The meaningful invariant is "the DELETED structure has no references" — not
# "a RETAINED accessor is mentioned exactly once". Guard the deleted structure, and
# scan scripts/ and tests/ too (the first-draft guards skipped those dirs).
grep -rn "\.voice\.\|AccountVoice\|default_negative_semantics\|format_negative_semantics" \
  backend/app backend/scripts backend/tests
grep -rn "negative_semantics" backend/app backend/scripts backend/tests frontend/src \
  --include=*.py --include=*.ts --include=*.tsx
grep -rn "voice-polish-rules\|useVoicePolishRules\|_BANNED_PHRASES\|select_polished_from_ranked" \
  backend/app frontend/src
```
> Do **not** grep `account\.system_prompt` as a cleanliness check: the `system_prompt` accessor is *retained* and has legitimate live callers (e.g. `runner.py` trace context, any tooling). Flagging those would be a false positive. The `.voice.`/`AccountVoice` guard above is the correct "old structure is gone" signal.

## b. Rebuild & run the stack

```bash
cd SocialMediaAutonomousAgents
docker compose up -d --build
docker ps --format "table {{.Names}}\t{{.Status}}"   # backend, frontend, nats healthy; ravendb healthy
```

## c. Run the migration

```bash
docker exec -it social-media-backend python -m scripts.migrate_voice_to_soul
# Expect: "Migrated JohnJames_News → soul (version=v… seq=…, N contrast, M punctuation)"
```
> **Expected one-time version bump (not a bug):** the first run bumps `seq` once and writes a
> single revision labeled **`soul-migration`**, because the hash payload changed (Task 05 now
> hashes the full soul). Re-running is a no-op (no further bump, no duplicate revision) — that is
> what "idempotent" means here. Verify by running the migration **twice**: the second run should
> log the same seq and add no new `/voice-revisions` entry.

## d. API verification

```bash
# Edit payload now returns the full soul (note: routes are under /api)
curl -s http://localhost:8000/api/accounts/JohnJames_News/edit | python -m json.tool
# Assert keys present: posting_prompt, personality, contrast_patterns[], punctuation_rules[],
#                      voice_version_label/seq/hash
# Assert ABSENT: system_prompt, negative_semantics

# Raw stored document migrated (voice dropped, soul present)
curl -s http://localhost:8000/api/accounts/JohnJames_News | python -m json.tool   # summary still OK

# Global rules endpoint is gone
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/voice-polish-rules   # expect 404

# Revisions carry soul snapshot
curl -s http://localhost:8000/api/accounts/JohnJames_News/voice-revisions | python -m json.tool

# Account snapshot endpoint still works (regression guard for the removed negative_semantics
# accessor in account_snapshot_service.py — see 02-voice-revision Addendum). Expect HTTP 201.
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8000/api/accounts/JohnJames_News/snapshot   # expect 201
```

**PATCH round-trip (version bump + revision):**
```bash
# Edit a soul field → expect v-bump and a new revision
curl -s -X PATCH http://localhost:8000/api/accounts/JohnJames_News \
  -H "Content-Type: application/json" \
  -d '{"contrast_patterns":[{"text":"avoid hedge words","correlation":"negative"},{"text":"short punchy openers","correlation":"positive"}]}' \
  | python -m json.tool
# Then re-GET /edit: voice_version_seq incremented; /voice-revisions has a new top entry.
```

## e. Compose behavior (the point of it all)

Trigger a forced compose and inspect the produced body:
```bash
# Option 1: existing helper
pwsh SocialMediaAutonomousAgents/scripts/docker-forced-post.ps1
# Option 2: force-post API/route used by the dashboard "force" control (see app/api/routes/force_post.py)
```
Checks on the composed text (via Posts explorer / Latest Run panel, or pipeline trace):
- **No em-dashes (— / –)** in opinion or quip (punctuation auto-fix applied).
- No double spaces; no space-before-punctuation; no leading punctuation.
- Reads consistent with contrast guidance (avoids the negative patterns; if a positive pattern exists, leans into it).
- Media URL intact at the end (per-block polishing didn't touch it).

> If `TICK_PIPELINE_TRACE` is enabled, inspect the `compose_*` trace step to see the pre/post text. Otherwise compare the stored post body.

## f. UI verification (`http://localhost:3000`)
Follow `08-frontend.md` → "UI interaction". Confirm:
- **Current soul** panel populated (personality, posting prompt, contrast patterns color-coded, punctuation rules monospace).
- **Voice polish rules** panel absent.
- Revision timeline `#N` entries expand to the soul snapshot.
- After the PATCH in (d), the badge shows the bumped version and a new revision row appears.
- **Edit-form regression check (`UpdateAccountModal`, see 08-frontend §c.2):** open Settings → Update, change the **Posting prompt**, Save; re-open the modal and confirm the new text persisted, and that the Voice tab badge bumped. (Pre-fix, this silently no-ops because the modal sent `system_prompt`, which the renamed PATCH body ignores.)
- **Legacy revision check (if any pre-refactor `voicerevisions/*` rows exist):** an old `#1` row still renders its real prompt/personality via the `system_prompt → posting_prompt` / `negative_semantics → contrast` fallback — NOT the current default contrast set. If it shows the defaults, the Task 02 correction (empty list defaults + legacy passthrough) was not applied.

## g. Definition of done (checklist)
- [ ] `py_compile` + `pytest` green; dead modules removed.
- [ ] `npm run build` clean; `useVoicePolishRules.ts` removed.
- [ ] Grep guards return nothing.
- [ ] Stack healthy after `--build`.
- [ ] Migration ran; stored doc has `soul`, no `voice`.
- [ ] `/edit` returns full soul; `/voice-polish-rules` → 404.
- [ ] PATCH bumps version + writes revision.
- [ ] Forced post body shows punctuation auto-fix + contrast guidance.
- [ ] Voice tab renders the full soul; legacy revisions still display their real (not default) content.
- [ ] **Snapshot endpoint works** — `POST` the account-snapshot route (`accounts.py:117`) returns 200 (proves the removed `negative_semantics` accessor was swept from `account_snapshot_service.py`).
- [ ] **Edit-form round-trips** — `UpdateAccountModal` posting-prompt edit persists and bumps the version (no silent `system_prompt` drop).
- [ ] **Migration is idempotent** — second run adds no new revision; first run's revision is labeled `soul-migration`.

---

## Rollback

The change is code + a forward data-migration. To roll back:

1. **Code:** `git revert` the implementation commit(s) (models, services, repository, compose, frontend). The pre-change code reads `voice` from documents.
2. **Data:** the migration rewrote `JohnJames_News` from `voice` → `soul`. The reverted code's `normalize_account_document` reads top-level/`voice` keys and will **not** find `voice`, so it will fall back to defaults for `system_prompt`/`negative_semantics` and lose the customized text. **Therefore:** before running the migration in production, snapshot the account:
   ```bash
   curl -s http://localhost:8000/api/accounts/JohnJames_News/edit > /tmp/jj_soul_backup.json
   # also export the raw RavenDB doc via Studio or the RavenDB API for a faithful restore
   ```
   To restore after a revert, PATCH the old fields back (`system_prompt`, `personality`, `negative_semantics`) from the backup.
3. **Revisions** are append-only and harmless to leave in place; the reverted code ignores the new soul fields on them.

> Because there is exactly one account and we snapshot it first, rollback risk is low. Take the snapshot in step (d) **before** the PATCH test so you also capture pre-edit state.

---

## Decision Defense

**Why run an explicit migration instead of relying on lazy on-save migration?**
Determinism and verifiability. We migrate on command, immediately assert the stored shape, and can re-run idempotently. (See `04-repository-and-migration.md`.)

**Why snapshot before migrating given the validator is non-destructive on read?**
Read is non-destructive, but the first **save** drops `voice`. A JSON snapshot of `/edit` (and the raw doc) guarantees a faithful restore path if we revert code afterward.

**Why verify compose output rather than trust unit tests?**
Unit tests confirm `polish_text`/prompt-formatting in isolation; only an end-to-end forced post proves the live `runner.py` path actually passes soul → prompt → polish → guardian and that the URL survives. Both layers matter.

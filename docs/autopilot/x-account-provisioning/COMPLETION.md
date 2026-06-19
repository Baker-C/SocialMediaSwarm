# X Account Provisioning — Completion Report

**Mission:** implement `docs/plans/x-account-provisioning/` end-to-end on `feat/x-account-provisioning`.
**Result:** all 9 units implemented and verified. 40 files new/changed. Backend, frontend, and the
standalone local-agent package all build and their tests pass.

## What was built

**Backend (`SocialMediaAutonomousAgents/backend/app/`)**
- `models/account.py` — `AccountProvisioning` + `ProvisioningImages` sub-document on `AccountDocument` (non-secret provisioning state).
- `models/account_secrets.py` + `services/account_secrets_repository.py` + `services/account_secrets_service.py` — encrypted `AccountSecrets` collection (Fernet, `_enc` fields, partial upsert, decrypt-on-read DTO).
- `services/persona_image_service.py` — avatar (`square_hd`) + header (`landscape_16_9`) via the existing fal/Seedream client + `MediaAssetRepository`.
- `api/routes/persona.py` + `persona_types.py` — persona-design chat (clone of agent_builder: stateless history, SSE worker, `messages_json_dict` → `PersonaDraft`), approve → images + account write, regenerate-images endpoint. Uses `ClaudeClient(model="claude-opus-4-8")`.
- `api/routes/provisioning.py` + `provisioning_types.py` + `services/provisioning_service.py` — two trust domains: frontend router (`start`/`status` SSE/`control`, under `require_auth`) + agent router (`job`/`status`/`control`/`result` + `email-code`/`phone`/`phone-code`, under `require_agent_token`).
- `infrastructure/disposable_email_client.py` + `disposable_phone_client.py` — provider-pluggable httpx clients (owned-domain catch-all email; SIM-based OTP phone).
- `api/routes/media.py` — `GET /api/media/{asset_id}` serving generated image bytes (registered WITHOUT auth so `<img src>` works; assets are non-sensitive uuids).
- `core/config.py` + `.env.example` — provisioning + card + disposable settings groups.
- `main.py` — registered persona, provisioning (frontend+agent), and media routers.

**Frontend (`SocialMediaAutonomousAgents/frontend/src/`)**
- `types/domain/persona.ts`, `api/endpoints/personaChat.ts` + `provisioning.ts`, `hooks/usePersonaChat.ts` + `useProvisioningStatus.ts` + `personaChatReducer.ts`, `components/ui/textarea.tsx`, `features/account-provisioning/AccountProvisioningPage.tsx` (chat → review → live status with CAPTCHA "Continue"), route `/provision` + "New Account" nav.

**Local agent (`SocialMediaAutonomousAgents/provisioning-agent/`, new package)**
- `agent/{config,types,backend_client,browser_port,selectors,page_state,orchestrator,run}.py` + 12 `handlers/` + ordered registry. `BrowserPort` protocol isolates Playwright (lazy import); detect→dispatch→report loop with re-enterable CAPTCHA pause and bounded retries. Self-contained types (no backend import). `tests/` with `FakeBrowser`/`FakeBackend`.

## Finishing-criteria evidence

```
# Full backend suite (from backend/):
$ python -m pytest -q
1 failed, 700 passed, 1 skipped, 1 warning in 5.31s
# the ONLY failure: tests/unit/test_act_artifacts_and_deps.py::test_artifacts_dict_has_16_entries
# (asserts 16, finds 19) — pre-existing, from the merged Seedance media tools.
# Proof it's not ours: `git status` shows artifacts.py and that test are NOT in our 40 changed files.

# New backend tests, individually green:
test_account_provisioning_model.py  4 passed
test_account_secrets_service.py     4 passed
test_persona_image_service.py       2 passed
test_persona_routes.py              6 passed
test_provisioning_service.py + test_provisioning_routes.py   15 passed
test_disposable_clients.py          13 passed
tests/integration/test_provisioning_e2e.py   1 passed
$ python -c "import app.main"   # clean

# Frontend (from frontend/):
$ CI=true npm run build         # Compiled successfully (tsc + lint clean)
$ react-scripts test (explicit --testMatch)   # 2 suites, 8 tests passed

# Local agent (from provisioning-agent/):
$ python -m pytest -q           # 37 passed   (no Playwright installed)
```

## Deferred / external (see BLOCKERS.md)
1. **Disposable providers** — clients + tests done; need a real owned email domain + mailbox API and a SIM-based OTP provider (configure via `.env`, reconcile request shapes).
2. **Agent selectors** — full structure + fake tests done; need the manual DOM spike (plan `09 §1`) to fill `agent/selectors.py`.
3. **Pre-existing media-artifacts test** — out of scope (Seedance merge), left untouched.
4. **Frontend test auto-discovery** — environmental (`.claude` path + micromatch escape); CI from a normal path is unaffected.

## Follow-ups
- Run the spike, fill selectors, then exercise the agent against the live flow.
- Provision the email domain + SIM OTP provider, set `.env`.
- (Optional) the pre-existing artifacts-count test should be updated by the media-tools owner.
- Changes are uncommitted on `feat/x-account-provisioning` (per the "commit only when asked" rule).

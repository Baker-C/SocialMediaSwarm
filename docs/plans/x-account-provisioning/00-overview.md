# X Account Provisioning — Implementation Plan (Overview)

> **Status:** Ready to implement. Authored in a planning session; pick up cold from this folder.
> **Scope:** Backend (models, encrypted secrets, persona chat, image gen, routes) + a new local
> browser-automation agent package + Frontend (persona page). **Scope 1 only** (account birth).
> **Target project:** `SocialMediaAutonomousAgents/` (backend = FastAPI + RavenDB, frontend = CRA/React).
> **Branch:** `feat/x-account-provisioning` off `origin/main`.

---

## 1. Why this exists

There is no UI to create an account today — only `scripts/add_account.py` and `POST /api/accounts`,
and neither does the *real-world* work: registering a fresh account on X, verifying it, setting up
the developer console / pay-per-use billing, and capturing the dev API keys. This plan makes that a
guided dashboard flow: **chat to design the persona → generate identity + images → drive the real
signup in a local browser → store the credentials encrypted.**

X actively resists automated signup (Arkose FunCaptcha, VoIP-number blocking, automation
fingerprinting). The architecture is shaped around *surviving* those defenses rather than pretending
they don't exist — see §3.

## 2. Component map

Eight components, each independently testable. The numbers are the plan files that own them.

| # | Component | Where it runs | New / reuse |
|---|---|---|---|
| 1 | `AccountProvisioning` sub-document (handle, name, bio, image refs, status) | backend model | **new**, extends `AccountDocument` |
| 2 | `AccountSecrets` encrypted collection + repo + service | backend | **new**, mirrors `oauth_token` |
| 3 | Persona-design chat → `PersonaDraft` spec | backend route + Claude | **new**, clones `agent_builder` |
| 4 | Avatar + header image generation | backend | **reuse** `fal_client` + `MediaAssetRepository` |
| 5 | `persona` + `provisioning` routers (SSE status, control) | backend route | **new**, clones SSE worker pattern |
| 6 | Local Provisioning Agent (Playwright + real Chrome) | **operator machine** | **new package** |
| 7 | Disposable email + SIM-phone clients | backend | **new** httpx clients |
| 8 | Persona page (chat, review, live status) | frontend | **new**, clones `useBuilderChat` |

The single best precedent for components 3, 5, and 8 is the existing **agent-builder**
(`backend/app/api/routes/agent_builder.py` + `frontend/src/features/builder/`): it already does
chat → structured draft → review → approve over SSE, stateless multi-turn, with the same Claude
client. We clone its shape rather than invent one.

## 3. The four load-bearing decisions (confirmed with the user)

1. **Browser runs locally on real Chrome (Option A).** The hosted FastAPI backend never runs
   Playwright. A separate `provisioning-agent/` package runs on the operator's machine against a
   real Chrome profile (residential IP, real fingerprint). The operator *watches the actual window*
   and solves the FunCaptcha there — no screenshot proxy, no noVNC. This is the highest-survival,
   lowest-infra option.
2. **Phone = SIM-based OTP service, conditional.** X blocks VoIP (Twilio etc.) in 2026. The phone
   handler only fires when X actually presents a phone wall (it allows email-only at low risk).
3. **CAPTCHA = human-in-the-loop.** The agent pauses on FunCaptcha; the operator solves it in the
   live window; the dashboard's "Continue" sets a control flag the agent polls. A solver API
   (CapSolver/2Captcha) is a deferred upgrade, not v1.
4. **Card in `.env`, used only if reached.** Pay-per-use billing setup auto-fills from `.env`. PCI
   note: CVV-in-`.env` is non-compliant; accepted for a throwaway personal project.

## 4. Communication design (no new transport patterns)

Deliberately **HTTP-only**, reusing the existing SSE-worker pattern. No WebSockets, no inbound port
on the agent.

```
Frontend ──► Backend     POST /api/provisioning/{account_id}/start
Frontend ◄── Backend     GET  /api/provisioning/{account_id}/status   (SSE, status events)
Frontend ──► Backend     POST /api/provisioning/{account_id}/control  {action:"continue"|"cancel"}

Agent    ◄── Backend     GET  /api/provisioning/{account_id}/job      (spec + disposable creds + card)
Agent    ──► Backend     POST /api/provisioning/{account_id}/status   (per-page progress)
Agent    ◄── Backend     GET  /api/provisioning/{account_id}/control  (poll; agent blocks on FunCaptcha)
Agent    ──► Backend     POST /api/provisioning/{account_id}/result   (dev keys, password, cookies → encrypted)
```

- The **agent never accepts inbound connections** and never talks to the frontend directly — it only
  makes outbound HTTP to the backend. This sidesteps CORS / mixed-content entirely.
- Agent requests carry a shared `PROVISIONING_AGENT_TOKEN` (config) in `Authorization`; a small
  dependency authorizes the agent-only routes (frontend routes keep the existing `require_auth`).
- Status fan-out to the frontend reuses the **worker/queue/SSE** pattern from
  `force_post.py` / `agent_builder.py` (sync worker thread → `asyncio.Queue` → `data: {json}\n\n`).
  The status stream's "worker" simply tails the `AccountProvisioning.status` the agent is POSTing.

> **Alternative considered (rejected for v1):** frontend → `http://localhost:<agent>` direct control.
> Lower latency but breaks under https/mixed-content and needs CORS on the agent. The HTTP-broker
> design above is more robust and reuses existing patterns. Documented here so it isn't re-litigated.

## 5. Established patterns this plan follows (from the live code)

| Concern | Pattern | Reference |
|---|---|---|
| Non-secret per-account state | nested `BaseModel` sub-document on `AccountDocument` + flat accessors | `AccountSoul`, `account.py` |
| Secrets | **separate** encrypted collection, `*_enc` fields, never on `AccountDocument` | `oauth_token.py`, `twitter_oauth2_service.py` |
| Encryption | Fernet via `app/utils/encryption.py`, single `ENCRYPTION_KEY` | `encryption.py:6-19` |
| Repository | lazy `client` property; `model_validate(_strip_metadata(raw))` read; `model_dump(exclude_none=True)` + explicit `collection=` write; `from @all` RQL fallback | `oauth_token_repository.py` |
| Service | `*Body` Pydantic model + `apply_*(body, repo=None)` | `account_create_service.py` |
| Job | `run_*_job(*, ..., repo=None)`, keyword-only, injectable repo | `create_account_job.py` |
| LLM structured output | prompt-for-JSON + `messages_json_dict` + `Model.model_validate` | `agent_builder.py:265` |
| Multi-turn chat | stateless: client echoes full history; server flattens to one user turn | `agent_builder.py:191` |
| Image gen | `get_fal_client().generate_image` → `fetch_bytes` → `MediaAssetRepository().save_bytes` | `seedance_image.py` |
| New router | `APIRouter()`, register in `main.py` under `dependencies=_auth` | `main.py:195-202` |
| SSE | sync worker → `asyncio.Queue` → `loop.call_soon_threadsafe` → `data: …\n\n` | `force_post.py:42-91` |
| Config | typed attr on the `Settings` singleton; auto env-map by name | `config.py:115-131` (fal block) |
| Tests | sync only, `unittest.mock` + `monkeypatch`, inject fakes, `TestClient`, auth auto-bypassed | `tests/conftest.py:12`, `test_media_tools.py` |

## 6. File-by-file task index

| # | Plan file | Backend touches | Frontend / other |
|---|---|---|---|
| 1 | `01-data-model.md` | `app/models/account.py` (+ `AccountProvisioning`) | — |
| 2 | `02-secrets-and-encryption.md` | `app/models/account_secrets.py`, `app/services/account_secrets_repository.py`, `app/services/account_secrets_service.py` | — |
| 3 | `03-persona-chat-and-spec.md` | `app/api/routes/persona.py`, `persona_types.py` | — |
| 4 | `04-image-generation.md` | `app/services/persona_image_service.py` | — |
| 5 | `05-backend-routes-and-orchestration.md` | `app/api/routes/provisioning.py`, `provisioning_types.py`, `app/services/provisioning_service.py`, `main.py`, `config.py` | — |
| 6 | `06-local-provisioning-agent.md` | — | `provisioning-agent/` package |
| 7 | `07-disposable-identity.md` | `app/infrastructure/disposable_email_client.py`, `disposable_phone_client.py`, `config.py`, `.env.example` | — |
| 8 | `08-frontend.md` | — | `features/account-provisioning/*`, hooks, endpoints, routes/nav |
| 9 | `09-testing-and-verification.md` | tests across all layers | spike protocol, done-criteria |

## 7. Sequencing

`01 → 02 → 04 → 03 → 05 → 07 → 08 → 06 → 09`

- **01–02 first:** everything persists into these; they round-trip independently with unit tests.
- **04 before 03:** the persona chat's "approve" step calls image gen, so the image service should exist first.
- **03 + 05:** chat produces the spec; provisioning routes consume it. 05 also adds config + `main.py` wiring.
- **07:** disposable identity clients (backend) — needed before the agent can fetch creds.
- **08:** frontend persona page — testable against the backend with the agent stubbed.
- **06 last + gated by a spike:** the local agent depends on X's live DOM and external services. Do the
  **manual end-to-end spike** (`09 §1`) *before* writing handlers, so the page-state machine is built
  against reality, not a guess.

> The backend half (01–05, 07–08) is fully buildable and testable **without** beating X — it has zero
> dependency on the agent. The agent (06) is the only piece exposed to X's defenses, and it's isolated
> behind the `BrowserPort` protocol so its logic is unit-testable without a browser.

## 8. Global definition of done

- `python -m py_compile` clean across touched backend files; `pytest` green (new tests added per layer).
- `npm run build` clean (no new TS errors); frontend Jest tests for the persona hook/page pass.
- Persona chat produces a validated `PersonaDraft`; "regenerate images" returns two `MediaAssets`.
- Approve writes an `AccountDocument` with a populated `AccountProvisioning` (status `draft`).
- `AccountSecrets` round-trips: write encrypted, read decrypted, ciphertext never leaves the backend.
- With the agent pointed at a **staging/sandbox flow** (see `09`), a dry-run drives page detection,
  pauses on FunCaptcha, resumes on Continue, and POSTs a result the backend stores encrypted.
- No secret (dev keys, password, cookies, card) is ever serialized into `AccountDocument` or any
  `*_view` / public route.

## 9. Risks & unknowns (carried, not hidden)

| Risk | Mitigation | Owner file |
|---|---|---|
| X signup DOM differs from assumptions | **spike first**; selectors centralized + data-driven | `06`, `09` |
| FunCaptcha appears multiple times / mid-flow | state machine treats CAPTCHA as a re-enterable state, not a one-shot | `06` |
| Disposable email domain blocklisted | use an **owned** domain + Cloudflare catch-all (most reliable) | `07` |
| SIM-phone service acceptance varies | conditional handler; pluggable provider; log failures | `06`, `07` |
| Claude client is single-shot (no native multi-turn/stream) | flatten-history like `agent_builder`; structured output via JSON-extract | `03` |
| `account_create_service` may not accept image refs | add image asset-id fields to `AccountProvisioning`, write via update path | `01`, `03` |
| Card-in-`.env` PCI exposure | accepted by user for throwaway use; isolated to one billing handler | `00 §3`, `06` |

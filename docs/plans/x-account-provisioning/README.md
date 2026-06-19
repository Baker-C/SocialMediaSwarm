# X Account Provisioning — Implementation Plan Set

Spin up a fresh X account end-to-end **from the dashboard**: design the persona by chatting
with Claude, generate the identity + avatar/header images, then drive the real X signup +
developer-console setup in a local browser (operator solves the CAPTCHA), and store the
account's dev credentials and login secrets encrypted per-account.

**Scope = Scope 1 only** (account birth → authenticated, API-ready account). Ongoing
engagement automation (post / reply / follow / like / quote) is **Scope 2, deliberately out
of this plan** — but the local browser agent built here is designed to be its future home.

**Start here:** [`00-overview.md`](./00-overview.md) — architecture, component map, the four
load-bearing decisions, sequencing, and done-criteria.

## Reading order
| # | File | What it covers |
|---|---|---|
| 0 | [00-overview.md](./00-overview.md) | Why, architecture, component map, decisions, comms design, sequencing, done |
| 1 | [01-data-model.md](./01-data-model.md) | `AccountProvisioning` sub-document on `AccountDocument` (non-secret state) |
| 2 | [02-secrets-and-encryption.md](./02-secrets-and-encryption.md) | `AccountSecrets` encrypted collection + repo + service (Fernet, `_enc`) |
| 3 | [03-persona-chat-and-spec.md](./03-persona-chat-and-spec.md) | Claude persona chat → `PersonaDraft` (modeled on `agent_builder`) |
| 4 | [04-image-generation.md](./04-image-generation.md) | Avatar + header via fal/Seedream + `MediaAssetRepository` |
| 5 | [05-backend-routes-and-orchestration.md](./05-backend-routes-and-orchestration.md) | `persona` + `provisioning` routers, SSE status, control poll |
| 6 | [06-local-provisioning-agent.md](./06-local-provisioning-agent.md) | New `provisioning-agent/` package: `BrowserPort`, page-state machine, handlers |
| 7 | [07-disposable-identity.md](./07-disposable-identity.md) | Disposable email + SIM-phone HTTP clients (backend) |
| 8 | [08-frontend.md](./08-frontend.md) | Persona page: chat panel, review, live status (copy `useBuilderChat`) |
| 9 | [09-testing-and-verification.md](./09-testing-and-verification.md) | Test plan per layer, spike, done-criteria, sequencing |

## Recommended implementation order
`01 → 02 → 04 → 03 → 05 → 07 → 08 → 06 → 09`

Rationale: storage first (models + encrypted secrets), then the image path, then the persona
chat that produces the spec, then the backend routes that tie chat + provisioning together,
then disposable identity, then the frontend, then the local agent (the riskiest, most
external-dependent piece — gated behind a manual **spike**, see `09`), then full verification.

## The flow, at a glance
```
┌─ Dashboard (operator's browser) ─────────────────────────────────────────┐
│  1. CHAT      Claude persona-design chat  ───────────────┐                │
│  2. REVIEW    edit handle/name/bio, regenerate images  ◄──┤ PersonaDraft   │
│  3. APPROVE   write account + AccountProvisioning(status=draft)            │
│  4. PROVISION live status stream + "solve CAPTCHA, Continue" button        │
└───────────┬───────────────────────────────────────────────▲──────────────┘
            │ start / SSE status / control:continue          │ status events
            ▼                                                 │
┌─ Backend (FastAPI) ───────────────────────────────────────┴──────────────┐
│  persona router (chat, SSE)   provisioning router (start, status, control) │
│  AccountRepository · AccountSecretsRepository(enc) · MediaAssetRepository  │
│  disposable email/phone clients                                           │
└───────────┬───────────────────────────────▲──────────────────────────────┘
            │ GET spec+creds · POST status · │ poll control · POST results
            ▼                                │
┌─ Local Provisioning Agent (operator machine, NEW package) ────────────────┐
│  Playwright + REAL Chrome (persistent profile, stealth)                    │
│  PageDetector → Handlers (fill/click/upload) → status; pause on FunCaptcha │
└───────────────────────────────────────────────────────────────────────────┘
         operator watches the real Chrome window; solves CAPTCHA there
```

## Decisions confirmed with the user (see `00 §3`)
- **Architecture:** Option A — local agent + **real Chrome** on the operator machine (best survival vs X bot defenses; CAPTCHA solved in the real window).
- **Phone:** **SIM-based** OTP service (VoIP/Twilio is hard-blocked by X in 2026); phone is a *conditional* step (X allows email-only at low risk).
- **CAPTCHA (Arkose FunCaptcha):** human solves in the live window; solver-API is a deferred upgrade.
- **Card data:** lives in **`.env`** (process-wide, single operator card) — used only when a pay-per-use billing page is actually reached. PCI/CVV risk accepted for a throwaway project.
- **Images:** **fal.ai/Seedream**, already on `main` (`infrastructure/fal_client.py`).
- **API tier:** pay-per-use (confirmed). Posting via the existing free/PPU API; follow/like/quote are Enterprise-only → Scope 2 browser automation.

## Target project paths
- Backend: `SocialMediaAutonomousAgents/backend/app/...`
- Frontend: `SocialMediaAutonomousAgents/frontend/src/...`
- New local agent: `SocialMediaAutonomousAgents/provisioning-agent/` (own `requirements.txt`; Playwright is **not** added to the hosted backend)
- DB reality: one account today (`JohnJames_News`); clean additions, no migration baggage.

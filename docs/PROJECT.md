# Social Media Autonomous Agents

Canonical documentation entry point for **what the codebase does today**. Subsystem docs under [`subsystems/`](subsystems/) describe each layer in detail.

## What this project is

A FastAPI backend with an in-process APScheduler autonomously posts plain-text tweets to **X (Twitter)** for multiple niche accounts stored in **RavenDB**. Each posting tick loads active accounts, pulls tweets from the account's **following home timeline** as reference material, ranks them, composes an opinion + quip + source link via **Claude** (or deterministic fallback), runs safety and niche-fit checks, posts to X, and records the tweet for engagement polling. There is **no human review queue**. A React dashboard reads account status from the API; account **creation** remains CLI-only ([ACCOUNT_SETUP](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md)).

## Repo layout

| Path | Contents |
|------|----------|
| `SocialMediaAutonomousAgents/backend/` | FastAPI app, jobs, hourly pipeline, social layer, RavenDB repos |
| `SocialMediaAutonomousAgents/frontend/` | React (CRA) operator dashboard |
| `SocialMediaAutonomousAgents/docker-compose.yml` | Backend + frontend containers |
| `SocialMediaAutonomousAgents/scripts/` | Host PowerShell helpers (docker up, forced post) |
| `docs/` | This documentation tree (canonical) |

## Subsystem index

| Doc | Covers | Key entry files |
|-----|--------|-----------------|
| [entry-and-runtime](subsystems/entry-and-runtime.md) | Process startup, APScheduler, Docker | `backend/app/main.py`, `backend/app/jobs/*.py` |
| [hourly-orchestration](subsystems/hourly-orchestration.md) | Tick gateway, guards, slot idempotency | `backend/app/hourly/runner.py`, `backend/app/agents/orchestrator.py` |
| [reference-ingestion](subsystems/reference-ingestion.md) | Timeline fetch, rank, cache, dedup | `backend/app/services/tick_data_service.py` |
| [compose-and-safety](subsystems/compose-and-safety.md) | LLM compose, length budget, safety | `backend/app/hourly/compose_timeline_post.py` |
| [hourly-crew-llm](subsystems/hourly-crew-llm.md) | Prompts, Claude client, alternate generate/rank | `backend/app/hourly_crew/`, `backend/app/infrastructure/claude_client.py` |
| [social-x-integration](subsystems/social-x-integration.md) | Tweepy X client, OAuth1/2 | `backend/app/social/implementations/x_client.py` |
| [persistence-ravendb](subsystems/persistence-ravendb.md) | Documents, repos, encryption | `backend/app/infrastructure/ravendb_http.py` |
| [engagement-and-metrics](subsystems/engagement-and-metrics.md) | `:05` poll job, metrics placeholder | `backend/app/jobs/engagement_job.py` |
| [api-and-dashboard](subsystems/api-and-dashboard.md) | FastAPI routes | `backend/app/api/routes/` |
| [frontend-dashboard](subsystems/frontend-dashboard.md) | React UI | `frontend/src/App.tsx` |
| [operations](subsystems/operations.md) | Docker, env, CLI scripts | `docker-compose.yml`, `backend/scripts/` |

Paths above are relative to `SocialMediaAutonomousAgents/`.

**Operational how-to:** [ACCOUNT_SETUP](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md) — provisioning accounts and credentials.

## How subsystems connect

```mermaid
flowchart TB
    PROJECT[PROJECT.md]
    ENTRY[entry-and-runtime]
    API[api-and-dashboard]
    ORCH[hourly-orchestration]
    REF[reference-ingestion]
    COMPOSE[compose-and-safety]
    CREW[hourly-crew-llm]
    SOCIAL[social-x-integration]
    RDB[persistence-ravendb]
    ENG[engagement-and-metrics]
    FE[frontend-dashboard]
    OPS[operations]

    PROJECT --> ENTRY & API & ORCH & FE & OPS

    ENTRY -->|APScheduler| ORCH
    ENTRY -->|APScheduler| ENG

    ORCH --> REF
    ORCH --> COMPOSE
    ORCH --> RDB
    ORCH --> SOCIAL

    REF --> SOCIAL
    REF --> RDB

    COMPOSE --> CREW
    COMPOSE --> SOCIAL

    ENG --> SOCIAL
    ENG --> RDB

    API --> RDB
    FE --> API
```

**Control flow for a scheduled post:**

1. **entry-and-runtime** — APScheduler fires `hourly_job` (respects quiet hours)
2. **hourly-orchestration** — loads accounts, applies guards, reserves slot
3. **reference-ingestion** — fetches timeline via **social-x-integration**, ranks, excludes copied refs
4. **compose-and-safety** — Claude compose (prompts from **hourly-crew-llm**), safety/niche checks
5. **hourly-orchestration** — posts via **social-x-integration**, persists to **persistence-ravendb**
6. **engagement-and-metrics** — later polls views/likes on tracked posts

## Suggested reading paths

| Goal | Read first | Then |
|------|------------|------|
| New contributor | This doc → [entry-and-runtime](subsystems/entry-and-runtime.md) | [hourly-orchestration](subsystems/hourly-orchestration.md) → [reference-ingestion](subsystems/reference-ingestion.md) → [compose-and-safety](subsystems/compose-and-safety.md) |
| Run the stack | [operations](subsystems/operations.md) | [backend/README](../SocialMediaAutonomousAgents/backend/README.md) |
| Add an account | [ACCOUNT_SETUP](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md) | [persistence-ravendb](subsystems/persistence-ravendb.md) |
| Debug a failed post | [hourly-orchestration](subsystems/hourly-orchestration.md) (skip reasons) | Enable `TICK_PIPELINE_TRACE=true` → [compose-and-safety](subsystems/compose-and-safety.md) |
| Dashboard behavior | [frontend-dashboard](subsystems/frontend-dashboard.md) | [api-and-dashboard](subsystems/api-and-dashboard.md) |
| X API / credentials | [social-x-integration](subsystems/social-x-integration.md) | [ACCOUNT_SETUP](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md) |

## Out of scope / not yet built

Verified from current code:

| Area | Status |
|------|--------|
| Human review queue before posting | Not implemented |
| `POST /api/accounts` for creation | Implemented (`PATCH` for updates) |
| `GET /api/posts`, `/patterns`, `/metrics/{id}` | Stub endpoints (empty or zeros) |
| Metrics job (`:10`) | Placeholder — does not populate dashboard `avg_engagement` |
| Alternate generate→rank pipeline (`hourly_crew/runner.py`) | Implemented but **not** wired into live tick |
| Trend tweet search as reference source | Disabled (`TREND_TWEET_SEARCH_ENABLED=false`) |
| Buffer posting integration | Config + sync scripts exist; live tick posts directly to X |
| Frontend live polling | `REACT_APP_POLLING_INTERVAL` unused — load-on-mount only |
| In-process RavenDB backups | Not implemented |

## Documentation index

All project documentation lives under this tree or is linked below. Paths under `SocialMediaAutonomousAgents/` are relative to that folder unless noted.

### Canonical (`docs/`)

| Doc | Role |
|-----|------|
| [PROJECT.md](PROJECT.md) | This entry point |
| [subsystems/entry-and-runtime.md](subsystems/entry-and-runtime.md) | Startup, APScheduler, Docker |
| [subsystems/hourly-orchestration.md](subsystems/hourly-orchestration.md) | Tick gateway, guards, slots |
| [subsystems/reference-ingestion.md](subsystems/reference-ingestion.md) | Timeline fetch, rank, cache |
| [subsystems/compose-and-safety.md](subsystems/compose-and-safety.md) | LLM compose, safety checks |
| [subsystems/hourly-crew-llm.md](subsystems/hourly-crew-llm.md) | Claude client, prompt inventory |
| [subsystems/social-x-integration.md](subsystems/social-x-integration.md) | Tweepy X client, OAuth |
| [subsystems/persistence-ravendb.md](subsystems/persistence-ravendb.md) | Documents, repos, encryption |
| [subsystems/engagement-and-metrics.md](subsystems/engagement-and-metrics.md) | Engagement poll, metrics job |
| [subsystems/api-and-dashboard.md](subsystems/api-and-dashboard.md) | FastAPI routes |
| [subsystems/frontend-dashboard.md](subsystems/frontend-dashboard.md) | React operator UI |
| [subsystems/operations.md](subsystems/operations.md) | Docker, env, CLI scripts |

### External / operational guides

| Doc | Role |
|-----|------|
| [ACCOUNT_SETUP](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md) | RavenDB prereqs, OAuth1/OAuth2 CLI provisioning |
| [backend/README](../SocialMediaAutonomousAgents/backend/README.md) | Backend venv, Docker, scripts |
| [frontend/README](../SocialMediaAutonomousAgents/frontend/README.md) | CRA dev server quick start |

### Runtime assets (not user-facing docs)

LLM prompt templates loaded at runtime: `backend/app/hourly_crew/prompts/` (see [hourly-crew-llm](subsystems/hourly-crew-llm.md) for file inventory). Edit those `.md` files in place; do not treat them as documentation.

### Removed / superseded

`ImplementationSpecifications/` (stage specs, setup guides, product plans) was removed; behavior is described only in `docs/` above.

# Social Media Autonomous Agents — Backend

FastAPI service with RavenDB (`SocialMediaSwarm` at `https://localhost`), encrypted per-account X (OAuth1) credentials, and an in-process **APScheduler** (scheduled posting every `POST_INTERVAL_MINUTES`, default 20; engagement **:05**, metrics **:10** each hour in `SCHEDULER_TIMEZONE`). **New accounts are created only via CLI** (`scripts/add_account.py` / `run_create_account_job`), not via HTTP.

## Setup

1. Python 3.11+ recommended.
2. Create a venv and install deps:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env`, set **`ENCRYPTION_KEY`** (Fernet) and optional **`SCHEDULER_TIMEZONE`** (IANA, e.g. `America/Chicago`).
4. Ensure RavenDB is running and the database exists.
5. Add at least one active account with X credentials (all four OAuth1 secrets are required):

```bash
python scripts/add_account.py --account-id my-handle ^
  --niche "Your niche" ^
  --twitter-handle "@myhandle" ^
  --twitter-api-key "..." ^
  --twitter-api-secret "..." ^
  --twitter-access-token "..." ^
  --twitter-access-token-secret "..."
```

6. **Docker-only (recommended)** — from repo root:

```powershell
docker compose -f $env:USERPROFILE\ravendb\docker-compose.yml up -d
docker compose up -d --build
```

Forced post (inside the backend container, not on the host):

```powershell
.\scripts\docker-forced-post.ps1 JohnJames_News
```

Local `uvicorn` is optional for development; do **not** run local `uvicorn` and Docker backend together (duplicate posts). The compose file sets `RUN_SCHEDULER=true` only on the container.

## Database backups

RavenDB **full database backups** are an **operations** concern (Studio scheduled backup, infrastructure snapshots, etc.). The hourly orchestrator **does not** run in-process database exports or binary backups.

## Optional: Claude (Anthropic)

For multi-candidate generation and ranking, set **`ANTHROPIC_API_KEY`** and optionally **`CLAUDE_MODEL`** (see `.env.example`). If unset, the pipeline falls back to deterministic candidate text.

## Scripts

| Script | Purpose |
|--------|---------|
| `python scripts/add_account.py --account-id ...` | Upsert account with encrypted OAuth1; see `--help` |
| `python scripts/account_setup_wizard.py` | Interactive prompts for the same |
| `python scripts/test_twitter_credentials.py` | Posts a short test tweet per active account |
| `docker compose exec backend python scripts/create_forced_post.py acc1` | Force post via Docker backend (preferred) |
| `python scripts/create_forced_post.py acc1 --force-now` | Bypass cooldown only; use inside container or when no Docker scheduler is running |

## API

- `GET /api/accounts` — redacted list  
- `GET /api/accounts/{id}`  
- `PATCH /api/accounts/{id}/archive` — set `inactive`  
- `GET /api/accounts/{id}/status` — `POST /api/accounts/{id}/test`  

Create or change credentials only via **`python scripts/add_account.py`** (or `run_create_account_job` from code).

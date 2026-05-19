# Backend Setup Guide — FastAPI + CrewAI + RavenDB

Operator guide for **SocialMediaAutonomousAgents** (`SocialMediaAutonomousAgents/backend`). Stage 1 behavior is documented in [`SocialMediaAutonomousAgents/docs/Stage_1_Implementation.md`](../SocialMediaAutonomousAgents/docs/Stage_1_Implementation.md).

---

## Recommended runtime: Docker only

Run **one** backend process with the scheduler. Do **not** run local `uvicorn` and the Docker backend on port 8000 at the same time — that causes **duplicate hourly posts** (two pipelines, two candidate pools).

| Service | How to run | URL |
|---------|------------|-----|
| **RavenDB** | `docker compose` in `%USERPROFILE%\ravendb` | https://localhost |
| **Backend + scheduler** | `docker compose` in repo root | http://localhost:8000 |
| **Frontend** | same compose file | http://localhost:3000 |

---

## Architecture (current)

| Layer | Location | Role |
|-------|----------|------|
| **API + scheduler** | `app/main.py`, `app/jobs/` | FastAPI, APScheduler (`:00` / `:05` / `:10`) |
| **Gateway / tick** | `app/hourly/runner.py`, `app/hourly/orchestration/` | Pre → crew → post; idempotency & guards |
| **LLM runtime** | `app/hourly_crew/` | Claude prompts, generate + rank |
| **X integration** | `app/social/`, `app/services/twitter_service.py` | Tweepy via OAuth1 or OAuth2 |
| **Persistence** | `app/services/account_repository.py`, `app/infrastructure/ravendb_http.py` | Accounts, `last_post_slot`, post locks |

```
SocialMediaAutonomousAgents/
├── docker-compose.yml          # backend + frontend (RavenDB is separate)
├── scripts/
│   ├── docker-up.ps1           # build + start app stack
│   └── docker-forced-post.ps1  # force post inside container
└── backend/
    ├── app/
    │   ├── main.py
    │   ├── hourly/             # tick orchestration
    │   │   ├── runner.py
    │   │   ├── tweet_topic_preanalysis.py
    │   │   └── orchestration/
    │   │       ├── pre_tick.py
    │   │       ├── post_tick.py
    │   │       ├── post_guard.py    # cooldown + locks
    │   │       └── slot_claim.py    # hourly slot reservation
    │   ├── hourly_crew/        # prompts + LLM pipeline
    │   ├── agents/orchestrator.py
    │   ├── jobs/               # hourly_job, engagement_job, metrics_job
    │   ├── api/routes/
    │   ├── services/
    │   └── social/
    ├── scripts/                # add_account, create_forced_post, …
    ├── docs/ACCOUNT_SETUP.md
    ├── .env.example
    └── Dockerfile
```

---

## Prerequisites

- **Docker Desktop** (engine running; `docker ps` works)
- **Python 3.12+** (only for host-side account scripts if you prefer; posting should use Docker)
- **RavenDB** with database **`SocialMediaSwarm`**
- **Client certificate** for RavenDB (PEMs under `%USERPROFILE%\ravendb\certs` or paths in env)
- **X API credentials** per account (OAuth 1.0a four fields or OAuth2 user token)
- Optional: **`ANTHROPIC_API_KEY`** for Claude candidate generation/ranking

---

## Step 1: RavenDB

RavenDB uses its own compose file (not the app `docker-compose.yml`):

```powershell
docker compose -f $env:USERPROFILE\ravendb\docker-compose.yml up -d
```

- Studio: https://localhost  
- Default app DB name: **`SocialMediaSwarm`** (`RAVENDB_DB` in `.env`)

If Studio returns **403 InvalidAuth**, set client cert paths in `backend/.env` or mount certs as in app compose (see Step 3).

---

## Step 2: Backend environment

```powershell
cd SocialMediaAutonomousAgents\backend
copy .env.example .env
```

Edit `backend/.env` (never commit):

| Variable | Purpose |
|----------|---------|
| `ENCRYPTION_KEY` | Fernet key for encrypted X tokens in RavenDB |
| `ANTHROPIC_API_KEY` | Claude for hourly content pipeline |
| `SCHEDULER_TIMEZONE` | IANA zone for `:00` jobs and slot key (`YYYY-MM-DD-H`) |
| `RAVENDB_URL` | Use `https://localhost` on host; Docker overrides to `host.docker.internal` |

Generate encryption key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

See `backend/.env.example` for optional: `CLAUDE_MODEL`, `TRENDS_PREFER_PERSONALIZED`, `TICK_PIPELINE_TRACE`, OAuth2 app keys.

---

## Step 3: Start app stack (Docker)

From repo root `SocialMediaAutonomousAgents/`:

```powershell
docker compose up -d --build
```

Or:

```powershell
.\scripts\docker-up.ps1
```

The backend container sets:

| Variable | Value | Notes |
|----------|-------|--------|
| `RAVENDB_URL` | `https://host.docker.internal` | Reach RavenDB on the host |
| `RAVENDB_CLIENT_CERT` / `KEY` | `/certs/...` | Mounted from `%USERPROFILE%\ravendb\certs` |
| `RUN_SCHEDULER` | `true` | Only this container should schedule jobs |
| `POST_COOLDOWN_MINUTES` | `55` | Min gap between posts per account |
| `POST_LOCK_TTL_SECONDS` | `600` | RavenDB lock TTL while a tick runs |

Override cert directory if needed:

```powershell
$env:RAVENDB_CERTS_DIR = "C:\path\to\ravendb\certs"
docker compose up -d --build
```

**Verify**

```powershell
curl http://localhost:8000/api/health
# {"status":"ok"}

docker logs social-media-backend 2>&1 | Select-String "APScheduler started"
```

API docs: http://localhost:8000/docs

---

## Step 4: Add accounts (CLI)

There is **no** `POST /api/accounts`. Provision via script (host or container):

```powershell
cd backend
python scripts/add_account.py --account-id JohnJames_News ^
  --niche "Political News" ^
  --twitter-handle "@JohnJames_News" ^
  --twitter-oauth2-access-token "..." ^
  --twitter-oauth2-refresh-token "..."
```

OAuth 1.0a requires all four: `--twitter-api-key`, `--twitter-api-secret`, `--twitter-access-token`, `--twitter-access-token-secret`.

Details: [`backend/docs/ACCOUNT_SETUP.md`](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md).

---

## Scheduler and posting guards

APScheduler (in the **Docker backend only**):

| Minute | Job | File |
|--------|-----|------|
| `:00` | Hourly posting | `app/jobs/hourly_job.py` → `Orchestrator.run_tick()` |
| `:05` | Engagement poll | `app/jobs/engagement_job.py` |
| `:10` | Metrics placeholder | `app/jobs/metrics_job.py` |

**Duplicate-post prevention (scheduled + force)**

1. **Hourly slot** — `last_post_slot` reserved in RavenDB before LLM work (`slot_claim.py`).
2. **Post cooldown** — default 55 minutes since `last_post_at` (`post_guard.py`).
3. **File lock** — `%TEMP%\sma_account_post\{account_id}.lock`.
4. **RavenDB lock** — document `post-locks/{account_id}`.
5. **Scheduler lock** — one APScheduler per machine (`sma_apscheduler.lock`).

Force mode **bypasses hourly slot** but still uses cooldown and locks unless you pass `--force-now`.

---

## Forced post (Docker)

Always run forced posts **inside** the backend container:

```powershell
.\scripts\docker-forced-post.ps1 JohnJames_News
```

Bypass cooldown only (locks still apply):

```powershell
.\scripts\docker-forced-post.ps1 -ForceNow JohnJames_News
```

Equivalent:

```powershell
docker compose exec backend python scripts/create_forced_post.py JohnJames_News
```

**Do not** run `python scripts/create_forced_post.py` on the host while the Docker backend is up.

---

## Frontend

Started by the same `docker compose` (port **3000**). It calls `REACT_APP_API_URL=http://localhost:8000`.

---

## Optional: local Python / uvicorn

For development without Docker:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If you use this:

- Set `RUN_SCHEDULER=false` in `.env` **or** stop the Docker backend — never both schedulers.
- Use `RAVENDB_URL=https://localhost` (not `host.docker.internal`).
- Do not run forced posts on the host while Docker backend is running.

---

## Scripts reference

| Script | Purpose |
|--------|---------|
| `scripts/docker-up.ps1` | `docker compose up -d --build` |
| `scripts/docker-forced-post.ps1` | Force post via container |
| `scripts/add_account.py` | Upsert account + encrypted credentials |
| `scripts/account_setup_wizard.py` | Interactive account setup |
| `scripts/create_forced_post.py` | Force tick (`--force-now` bypasses cooldown) |
| `scripts/test_twitter_credentials.py` | Smoke post per account |

---

## HTTP API (read / ops)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/health` | Liveness |
| GET | `/api/accounts` | Redacted account list |
| GET | `/api/accounts/{id}` | Single account |
| GET | `/api/accounts/{id}/status` | Slot / post counts |
| PATCH | `/api/accounts/{id}/archive` | Set inactive |
| POST | `/api/accounts/{id}/test` | **Posts a test tweet** — avoid during automation |
| GET | `/api/posts`, `/api/dashboard`, `/api/patterns`, `/api/metrics` | Dashboard data |

Create or rotate credentials only via **`add_account.py`**, not HTTP.

---

## Running tests

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest
```

Key suites: `tests/test_orchestrator.py`, `tests/test_post_guard.py`, `tests/test_tweet_topic_preanalysis.py`.

---

## Troubleshooting

### Duplicate posts (two different tweets / candidate pools)

- **Cause:** Two backends (Docker + local `uvicorn`) or forced post on host while container scheduler runs.
- **Fix:** One backend only; use `docker-forced-post.ps1`; rebuild image after code changes: `docker compose build backend && docker compose up -d backend`.

### `docker ps` fails or 500 from Docker API

- Start **Docker Desktop** and wait for **Engine running**; retry `docker ps`.

### RavenDB connection refused from container

- RavenDB must be up on the host.
- Confirm compose sets `RAVENDB_URL=https://host.docker.internal` and certs are mounted.

### Forced post skipped: `posted_within_cooldown_*`

- Expected within `POST_COOLDOWN_MINUTES` (55).
- Use `-ForceNow` only when intentional.

### Forced post skipped: `account_post_lock_held` / `ravendb_post_lock_held`

- Another tick is in progress; wait for it to finish.

### Stale Docker image (old code)

```powershell
docker compose build --no-cache backend
docker compose up -d backend
docker exec social-media-backend python -c "import app.hourly.runner; print('ok')"
```

---

## Related docs

- [`SocialMediaAutonomousAgents/docs/Stage_1_Implementation.md`](../SocialMediaAutonomousAgents/docs/Stage_1_Implementation.md) — pipeline steps, prompts, pre-analysis
- [`SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md`](../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md) — account CLI details
- [`SocialMediaAutonomousAgents/backend/README.md`](../SocialMediaAutonomousAgents/backend/README.md) — short backend readme

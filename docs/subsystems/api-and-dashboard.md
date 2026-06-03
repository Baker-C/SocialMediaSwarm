# API and dashboard backend

Scope: FastAPI HTTP layer consumed by the React dashboard and operators. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/main.py` | App factory, CORS, router mounts under `/api` |
| `SocialMediaAutonomousAgents/backend/app/api/routes/health.py` | Liveness |
| `SocialMediaAutonomousAgents/backend/app/api/routes/accounts.py` | Account list, edit, archive, test post, pulled tweets |
| `SocialMediaAutonomousAgents/backend/app/api/routes/dashboard.py` | Aggregate dashboard stats |
| `SocialMediaAutonomousAgents/backend/app/api/routes/posts.py` | Posts list (stub) |
| `SocialMediaAutonomousAgents/backend/app/api/routes/patterns.py` | Patterns list (stub) |
| `SocialMediaAutonomousAgents/backend/app/api/routes/metrics.py` | Per-account metrics (stub) |
| `SocialMediaAutonomousAgents/backend/app/services/ravendb_service.py` | Read models for API responses |
| `SocialMediaAutonomousAgents/backend/app/services/account_update_service.py` | PATCH account updates from dashboard |
| `SocialMediaAutonomousAgents/backend/app/services/account_create_service.py` | POST account creation |

## Middleware

CORS allows `localhost` / `127.0.0.1` on any port (regex) plus explicit 3000/3001 origins. Credentials allowed; all methods/headers.

## Routes (current behavior)

All routes are prefixed with `/api`.

### Health

| Method | Path | Response |
|--------|------|----------|
| GET | `/health` | `{"status": "ok"}` |

### Accounts

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/accounts` | All accounts, **redacted** (no secrets); includes `recent_post`, `has_credentials` |
| GET | `/accounts/{id}` | Single account summary or 404 |
| GET | `/accounts/{id}/edit` | Non-secret fields for update modal |
| POST | `/accounts` | Create account with encrypted X credentials (409 if id exists) |
| PATCH | `/accounts/{id}` | Update niche, handle, status, prompts, Buffer ids, optional credential rotation |
| PATCH/DELETE | `/accounts/{id}/archive` | Sets `status=inactive` |
| GET | `/accounts/{id}/status` | `last_interval_slot`, `posts_total` |
| POST | `/accounts/{id}/test` | Posts a short credential test tweet via X |
| GET | `/accounts/{id}/pulled-tweets` | Stored reference tweets (`limit`, optional `since`) |

Account provisioning details: [ACCOUNT_SETUP](../../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md).

### Dashboard aggregates

| Method | Path | Response |
|--------|------|----------|
| GET | `/dashboard` | `active_accounts`, `top_niche` (mode of niches), `avg_engagement` (currently `0.0`) |

### Stubs

| Method | Path | Current behavior |
|--------|------|------------------|
| GET | `/posts` | Empty list `[]` |
| GET | `/patterns` | Empty list `[]` |
| GET | `/metrics/{account_id}` | `{account_id, avg_engagement_rate: 0.0, health_score: 0}` |

RavenDB read failures degrade to empty/zero data with logged warnings rather than crashing the process.

## Frontend consumption

The dashboard loads these in parallel on mount: `health`, `accounts`, `posts`, `patterns`, `dashboard`. See [frontend-dashboard](frontend-dashboard.md).

## Related docs

- Data backing reads: [persistence-ravendb](persistence-ravendb.md)
- X test post / credentials: [social-x-integration](social-x-integration.md)
- UI: [frontend-dashboard](frontend-dashboard.md)

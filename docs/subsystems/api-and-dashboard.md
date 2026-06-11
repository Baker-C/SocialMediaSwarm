# API and dashboard backend

Scope: FastAPI HTTP layer consumed by the React analytics dashboard and operators. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/main.py` | App factory, CORS, router mounts under `/api` |
| `SocialMediaAutonomousAgents/backend/app/api/routes/health.py` | Liveness |
| `SocialMediaAutonomousAgents/backend/app/api/routes/accounts.py` | Account CRUD, edit, archive, test post, pulled tweets, account snapshots |
| `SocialMediaAutonomousAgents/backend/app/api/routes/analytics.py` | Tracked posts, post snapshots, account metrics doc, pipeline outcomes, voice revisions |
| `SocialMediaAutonomousAgents/backend/app/api/routes/dashboard.py` | Aggregate dashboard stats |
| `SocialMediaAutonomousAgents/backend/app/api/routes/posts.py` | Fleet tracked-post rollup (`GET /posts`) |
| `SocialMediaAutonomousAgents/backend/app/api/routes/force_post.py` | On-demand force post (JSON or SSE) |
| `SocialMediaAutonomousAgents/backend/app/api/routes/oauth.py` | X OAuth2 connect / status / disconnect |
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
| PATCH | `/accounts/{id}` | Update niche, handle, status, prompts, `search_queries`, Buffer ids, optional credential rotation |
| PATCH/DELETE | `/accounts/{id}/archive` | Sets `status=inactive` |
| GET | `/accounts/{id}/status` | `last_interval_slot`, `posts_total` |
| POST | `/accounts/{id}/test` | Posts a short credential test tweet via X |
| GET | `/accounts/{id}/pulled-tweets` | Stored reference tweets (`limit`, optional `since`) |
| GET | `/accounts/{id}/snapshots` | Account metric snapshots (newest first) |
| POST | `/accounts/{id}/force-post` | Run force-post pipeline for one account. Default: JSON result. With `Accept: text/event-stream`: SSE progress events (`progress`, `complete`, `error`). |

Account provisioning details: [ACCOUNT_SETUP](../../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md).

### Analytics (tracked posts, outcomes, voice)

Router: `api/routes/analytics.py`. Used by dashboard pages under `frontend/src/features/`.

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/accounts/{id}/tracked-posts` | `TrackedPosts` for account (`limit`, optional `since` ISO filter) |
| GET | `/accounts/{id}/posts/{tweet_id}` | Single tracked post document |
| GET | `/accounts/{id}/posts/{tweet_id}/snapshots` | `PostMetricSnapshot` time series for one tweet |
| GET | `/accounts/{id}/account-metrics` | Latest `AccountMetrics` document or 404 |
| GET | `/accounts/{id}/pipeline-outcomes` | Pipeline outcome rows (`since`, `limit`, optional `phase`, `status`) |
| GET | `/accounts/{id}/voice-revisions` | Voice revision history |
| GET | `/pipeline-outcomes` | Fleet-wide outcomes (optional `account_id`, `since`, `limit`, `phase`, `status`) |

Pipeline outcome `phase` values include runbook steps such as `runbook:load_account_bundle` and dotted composite ids like `runbook:summarize_for_compose.analyze_external_references.rank_external_references` (see [pipeline-runbook](pipeline-runbook.md)).

### OAuth (X)

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/oauth/x/authorize` | Start OAuth2 PKCE (query: `account_id`) |
| GET | `/oauth/x/callback` | Token exchange (browser redirect) |
| GET | `/oauth/x/status/{account_id}` | Connection status |
| DELETE | `/oauth/x/disconnect/{account_id}` | Remove stored tokens |
| GET | `/oauth/x/setup` | Portal setup hints for operators |

### Dashboard aggregates

| Method | Path | Response |
|--------|------|----------|
| GET | `/dashboard` | `active_accounts`, `top_niche` (mode of niches), `avg_engagement` (currently `0.0`) |

### Fleet posts rollup

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/posts` | Recent tracked posts across active accounts (`limit_per_account`, default 10) |

RavenDB read failures degrade to empty/zero data with logged warnings rather than crashing the process.

## Frontend consumption

The dashboard uses TanStack Query hooks that call analytics and account endpoints on demand per route. See [frontend-dashboard](frontend-dashboard.md).

## Related docs

- Data backing reads: [persistence-ravendb](persistence-ravendb.md)
- Engagement metrics on tracked posts: [engagement-and-metrics](engagement-and-metrics.md)
- X test post / credentials: [social-x-integration](social-x-integration.md)
- UI routes and hooks: [frontend-dashboard](frontend-dashboard.md)

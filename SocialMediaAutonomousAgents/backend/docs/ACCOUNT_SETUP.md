# Account setup (Option 4)

## Prerequisites

- RavenDB reachable at `https://localhost` (or override `RAVENDB_URL`), database `**SocialMediaSwarm**`. If Studio uses a **client certificate**, either set `**RAVENDB_CLIENT_CERT`** / `**RAVENDB_CLIENT_KEY**` in `backend/.env`, or put PEMs under `**%USERPROFILE%\ravendb\certs**` (e.g. `client.pem` plus optional `client.key`) — see `.env.example`.
- `backend/.env` with a valid `**ENCRYPTION_KEY**` (Fernet, url-safe base64). Generate:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do **not** commit `.env` or keys. Use `.env.example` as a template only.

## Adding an account

Choose **one** auth mode:

- **OAuth 2.0 user** — `twitter_oauth2_access_token` (and optional `twitter_oauth2_refresh_token`). Stored encrypted; clears OAuth1 fields on the document.
- **OAuth 1.0a** — all four `twitter_api_key`, `twitter_api_secret`, `twitter_access_token`, `twitter_access_token_secret` are required; clears OAuth2 token fields on the document.

### HTTP API

```http
POST /api/accounts
Content-Type: application/json

{
  "account_id": "my-handle",
  "niche": "Your niche",
  "twitter_handle": "@myhandle",
  "twitter_api_key": "...",
  "twitter_api_secret": "...",
  "twitter_access_token": "...",
  "twitter_access_token_secret": "..."
}
```

OAuth 2.0 example body: `account_id`, `niche`, `twitter_handle`, `twitter_oauth2_access_token`, optional `twitter_oauth2_refresh_token`.

Update an existing account (non-secret fields and credential rotation):

```http
PATCH /api/accounts/{account_id}
```

Load the edit form: `GET /api/accounts/{account_id}/edit`.

Returns **409** if `account_id` already exists on create; **404** if missing on patch.

### CLI (same logic as POST)

```bash
cd backend
python scripts/add_account.py --account-id my-handle ^
  --niche "Your niche" ^
  --twitter-handle "@myhandle" ^
  --twitter-api-key "..." ^
  --twitter-api-secret "..." ^
  --twitter-access-token "..." ^
  --twitter-access-token-secret "..."
```

OAuth 2.0 example:

```bash
python scripts/add_account.py --account-id my-handle --niche "Your niche" ^
  --twitter-handle "@myhandle" --twitter-oauth2-access-token "..." --twitter-oauth2-refresh-token "..."
```

Or pass `--json-file path/to/account.json` with `account_id`, `niche`, `twitter_handle`, and either the four OAuth1 `twitter_*` fields or `twitter_oauth2_access_token` / `twitter_oauth2_refresh_token`.

## Scheduler

With the backend running, **APScheduler** (when `RUN_SCHEDULER=true`) fires:

- **Posting** — every `POST_INTERVAL_MINUTES` on aligned minute marks (see `docker-compose.yml` / `.env`)
- **:05** — engagement poll on tracked posts
- **:10** — metrics job (placeholder)

Timezone: `**SCHEDULER_TIMEZONE`** (IANA). Slot idempotency uses the same zone. Details: `[docs/PROJECT.md](../../../docs/PROJECT.md)` → [entry-and-runtime](../../../docs/subsystems/entry-and-runtime.md).

## Frontend

The React dashboard: `[docs/subsystems/frontend-dashboard.md](../../../docs/subsystems/frontend-dashboard.md)`. Set `**REACT_APP_API_URL=http://localhost:8000**` when pointing at this backend.
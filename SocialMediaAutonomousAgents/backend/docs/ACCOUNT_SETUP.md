# Account setup (Option 4)

## Prerequisites

- RavenDB reachable at `https://localhost` (or override `RAVENDB_URL`), database **`SocialMediaSwarm`**. If Studio uses a **client certificate**, either set **`RAVENDB_CLIENT_CERT`** / **`RAVENDB_CLIENT_KEY`** in `backend/.env`, or put PEMs under **`%USERPROFILE%\ravendb\certs`** (e.g. `client.pem` plus optional `client.key`) — see `.env.example`.
- `backend/.env` with a valid **`ENCRYPTION_KEY`** (Fernet, url-safe base64). Generate:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- X Developer App with OAuth 2.0 enabled:
  - `TWITTER_OAUTH2_CLIENT_ID` / `TWITTER_OAUTH2_CLIENT_SECRET`
  - Callback URL: `TWITTER_OAUTH2_REDIRECT_URI` (default `http://localhost:8000/api/oauth/x/callback`)

Do **not** commit `.env` or keys. Use `.env.example` as a template only.

## Adding an account

1. Create the account profile (no tokens in the account document).
2. Connect X OAuth at runtime — tokens are stored in the separate `OAuthTokens` collection.

### HTTP API — create profile

```http
POST /api/accounts
Content-Type: application/json

{
  "account_id": "my-handle",
  "niche": "Your niche",
  "twitter_handle": "@myhandle"
}
```

### HTTP API — connect X OAuth

```http
GET /api/oauth/x/authorize?account_id=my-handle
```

Open the returned `authorization_url` in a browser, authorize as the X user, and the callback stores encrypted access + refresh tokens.

Check connection:

```http
GET /api/oauth/x/status/my-handle
```

Update profile fields:

```http
PATCH /api/accounts/{account_id}
```

Returns **409** if `account_id` already exists on create; **404** if missing on patch.

### CLI (profile only)

```bash
cd backend
python scripts/add_account.py --account-id my-handle ^
  --niche "Your niche" ^
  --twitter-handle "@myhandle"
```

Then connect OAuth via `GET /api/oauth/x/authorize?account_id=my-handle`.

## Scheduler

With the backend running, **APScheduler** (when `RUN_SCHEDULER=true`) fires:

- **Posting** — every `POST_INTERVAL_MINUTES` on aligned minute marks (see `docker-compose.yml` / `.env`)
- **:05** — engagement poll on tracked posts
- **:10** — metrics job (placeholder)
- **OAuth refresh** — every `OAUTH2_REFRESH_INTERVAL_MINUTES` (proactive token rotation)

Timezone: **`SCHEDULER_TIMEZONE`** (IANA). Slot idempotency uses the same zone. Details: [`docs/PROJECT.md`](../../../docs/PROJECT.md) → [entry-and-runtime](../../../docs/subsystems/entry-and-runtime.md).

## Frontend

The React dashboard: [`docs/subsystems/frontend-dashboard.md`](../../../docs/subsystems/frontend-dashboard.md). Set **`REACT_APP_API_URL=http://localhost:8000`** when pointing at this backend.

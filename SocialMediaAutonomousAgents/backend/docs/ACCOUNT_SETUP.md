# Account setup (Option 4)

## Prerequisites

- RavenDB reachable at `https://localhost` (or override `RAVENDB_URL`), database **`SocialMediaSwarm`**. If Studio uses a **client certificate**, either set **`RAVENDB_CLIENT_CERT`** / **`RAVENDB_CLIENT_KEY`** in `backend/.env`, or put PEMs under **`%USERPROFILE%\ravendb\certs`** (e.g. `client.pem` plus optional `client.key`) — see `.env.example`.
- `backend/.env` with a valid **`ENCRYPTION_KEY`** (Fernet, url-safe base64). Generate:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do **not** commit `.env` or keys. Use `.env.example` as a template only.

## Adding an account (CLI only)

There is **no** `POST /api/accounts` — provisioning uses the same job logic as the scripts below. Choose **one** auth mode:

- **OAuth 2.0 user** — pass `--twitter-oauth2-access-token` (and optional `--twitter-oauth2-refresh-token`). Stored encrypted; clears OAuth1 fields on the document.
- **OAuth 1.0a** — all four `--twitter-api-key`, `--twitter-api-secret`, `--twitter-access-token`, `--twitter-access-token-secret` are required; clears OAuth2 token fields on the document.

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

With `uvicorn` running, **APScheduler** fires:

- **:00** — hourly posting job (every active account in RavenDB)
- **:05** — engagement job (placeholder until posts are stored)
- **:10** — metrics job (placeholder)

Timezone: set **`SCHEDULER_TIMEZONE`** (IANA). Idempotency uses the same zone for the hourly slot key.

## Frontend

The React app uses Create React App (`frontend/README.md`). Set **`REACT_APP_API_URL=http://localhost:8000`** when pointing at this backend.

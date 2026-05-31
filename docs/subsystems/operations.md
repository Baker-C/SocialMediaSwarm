# Operations

Scope: Docker deployment, environment variables, CLI scripts, and operator workflows. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/docker-compose.yml` | Backend + frontend stack |
| `SocialMediaAutonomousAgents/backend/.env.example` | Environment template |
| `SocialMediaAutonomousAgents/scripts/docker-up.ps1` | Start compose from repo app root |
| `SocialMediaAutonomousAgents/scripts/docker-forced-post.ps1` | Force post via container |
| `SocialMediaAutonomousAgents/backend/scripts/add_account.py` | Account provisioning CLI |
| `SocialMediaAutonomousAgents/backend/scripts/account_setup_wizard.py` | Interactive account setup |
| `SocialMediaAutonomousAgents/backend/scripts/create_forced_post.py` | Manual posting tick |
| `SocialMediaAutonomousAgents/backend/scripts/test_twitter_credentials.py` | Credential smoke test |
| `SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md` | Detailed account setup guide |

## Docker stack

RavenDB is **not** in this compose file. Typical startup:

```powershell
docker compose -f $env:USERPROFILE\ravendb\docker-compose.yml up -d
cd SocialMediaAutonomousAgents
docker compose up -d --build
```

Backend container:

- Port **8000**, `RUN_SCHEDULER=true`
- RavenDB at `host.docker.internal` with mounted client certs (`RAVENDB_CERTS_DIR`)
- Scheduler overrides in compose (interval, quiet hours, force mode)

Frontend container:

- Port **3000**, `REACT_APP_API_URL=http://localhost:8000`

**Do not** run local `uvicorn` and Docker backend together — duplicate schedulers cause duplicate posts.

## Critical environment variables

| Variable | Purpose |
|----------|---------|
| `ENCRYPTION_KEY` | Fernet key for credential encryption (required) |
| `RAVENDB_URL`, `RAVENDB_DB` | Database connection |
| `RAVENDB_CLIENT_CERT`, `RAVENDB_CLIENT_KEY` | mTLS to RavenDB |
| `RUN_SCHEDULER` | Enable in-process APScheduler |
| `SCHEDULER_TIMEZONE` | IANA zone for jobs and slot keys |
| `POST_INTERVAL_MINUTES`, `POST_COOLDOWN_MINUTES` | Posting cadence |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Claude for compose/safety |
| `BUFFER_API_KEY` | Buffer integration (optional; sync scripts exist) |

Full list: `backend/app/core/config.py` and `.env.example`.

## Common scripts

| Command | Purpose |
|---------|---------|
| `python scripts/add_account.py --account-id ...` | Create/update account with encrypted creds |
| `python scripts/create_forced_post.py acc1 --force-now` | Force post (use inside container when scheduler runs) |
| `python scripts/test_twitter_credentials.py` | Post test tweet per active account |
| `.\scripts\docker-forced-post.ps1 JohnJames_News` | Host wrapper for forced post in container |

## Database backups

RavenDB full backups are an **operations** concern (Studio scheduled backup, infrastructure snapshots). The app does not run in-process database exports.

## Related docs

- Runtime / scheduler: [entry-and-runtime](entry-and-runtime.md)
- Account provisioning detail: [ACCOUNT_SETUP](../../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md)
- Backend quick start: [backend/README](../../SocialMediaAutonomousAgents/backend/README.md)

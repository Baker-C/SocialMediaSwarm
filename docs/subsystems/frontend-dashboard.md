# Frontend dashboard

Scope: React operator UI and its coupling to the FastAPI backend. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/frontend/src/App.tsx` | Main dashboard, account cards, update modal |
| `SocialMediaAutonomousAgents/frontend/src/App.css` | Layout / bento styling |
| `SocialMediaAutonomousAgents/frontend/src/index.tsx` | CRA entry |
| `SocialMediaAutonomousAgents/frontend/package.json` | Dependencies, scripts |
| `SocialMediaAutonomousAgents/frontend/Dockerfile` | Production container |
| `SocialMediaAutonomousAgents/docker-compose.yml` | `REACT_APP_API_URL`, port 3000 |

## Structure

Single-page app (Create React App). No client-side router — one view at `/`.

Sidebar tabs (see `navigation/tabs.ts`):

| Tab | Panel |
|-----|--------|
| Overview | Fleet stats, account list with Open → account tab |
| One per account | Full account detail (`AccountCard`) |

| Path | Purpose |
|------|---------|
| `App.tsx` | API load, tab state, shell layout |
| `navigation/tabs.ts` | `TabId`, `buildNavItems` — add new tabs here |
| `navigation/Sidebar.tsx` | Sidebar tab list |
| `panels/renderPanel.tsx` | Maps `TabId` → panel component |
| `panels/OverviewPanel.tsx` | Overview content |
| `panels/AccountPanel.tsx` | Single-account view |
| `components/AccountCard.tsx` | Account stats and update button |
| `components/UpdateAccountModal.tsx` | PATCH account + credentials |

## API coupling

On mount, parallel fetches to `{apiBase}/api/{endpoint}` for:

`health`, `accounts`, `posts`, `patterns`, `dashboard`

| Env var | Effect |
|---------|--------|
| `REACT_APP_API_URL` | Backend origin (compose: `http://localhost:8000`) |
| Dev proxy | Empty base → CRA proxies `/api` to `127.0.0.1:8000` |

Update flow:

- GET `/api/accounts/{id}/edit` — populate modal
- PATCH `/api/accounts/{id}` — save changes

Polling interval env `REACT_APP_POLLING_INTERVAL` is defined in compose but **not** used in `App.tsx` today (load-on-mount only).

## UI sections

1. **Sidebar** — Overview + one tab per account (sorted by `account_id`)
2. **Overview panel** — bento stats + account list; debug JSON in `<details>`
3. **Account panel** — full-width account card for the selected tab

Stub endpoints (`/posts`, `/patterns`) are fetched but not displayed in the main UI.

## Development

```bash
cd SocialMediaAutonomousAgents/frontend
npm install
npm start   # http://localhost:3000
```

Backend must be on port 8000. See [frontend/README](../../SocialMediaAutonomousAgents/frontend/README.md) for CRA commands.

## Related docs

- API routes: [api-and-dashboard](api-and-dashboard.md)
- Runtime / Docker: [entry-and-runtime](entry-and-runtime.md)

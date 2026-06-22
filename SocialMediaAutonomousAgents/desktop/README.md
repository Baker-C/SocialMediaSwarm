# X Provisioning Desktop (Electron)

A thin Electron host that loads the existing dashboard and embeds the X-signup
flow in a `<webview>`. The webview autofills every field from the backend (name,
email, generated password, email/SMS code, phone) so the operator only clicks
**Next** and solves the Arkose CAPTCHA. Each account signs up in its own isolated
session partition (`persist:acct_<id>`), and the OAuth connect runs in that SAME
partition — so the resulting token binds to that account only.

## Why a webview (not an iframe)

`<iframe src="x.com">` renders blank: X sends `X-Frame-Options` /
`frame-ancestors 'none'`. An Electron `<webview>` is a separate Chromium guest,
not an in-page iframe, so the framing block doesn't apply and x.com loads.

## How it fits together

- `main.js` — Electron main process. Opens a `BrowserWindow` (with
  `webPreferences.webviewTag = true`) pointed at the dashboard. Registers a single
  IPC handler (`prov:action`) that the webview preload calls; main attaches
  `Authorization: Bearer ${PROVISIONING_AGENT_TOKEN}` and hits the backend. This
  keeps the token in main and avoids CORS. Actions mirror the browser extension's
  `background.js`: `getJob`, `emailCode`, `acquirePhone`, `smsCode`,
  `genPassword`, plus `authorizeUrl` (`GET /oauth/x/authorize?account_id=...`).
- `autofill-preload.js` — the `<webview>` preload. A `MutationObserver` watches
  for the signup fields; when one appears it asks main for the data over IPC and
  fills it with the React-safe setter+dispatch technique (ported verbatim from
  `provisioning-extension/content.js`). It never auto-clicks Next/submit.
- `frontend/src/features/provisioning/SignupWebview.tsx` — the React component
  (Electron-only) that renders the `<webview partition="persist:acct_<id>">` and
  the **Continue → connect** control that navigates the same webview to the OAuth
  authorize URL after signup.

## Run

1. **Start backend + frontend** (Dockerized as usual):

   ```sh
   docker compose up    # backend on :8000, dashboard on :3000
   ```

2. **Set the agent token** (same value the provisioning agent / extension uses):

   ```sh
   export PROVISIONING_AGENT_TOKEN="<token>"
   # optional overrides:
   # export DASHBOARD_URL="http://localhost:3000"
   # export BACKEND_URL="http://localhost:8000/api"
   ```

   On Windows PowerShell:

   ```powershell
   $env:PROVISIONING_AGENT_TOKEN = "<token>"
   ```

3. **Install + launch Electron** (from this `desktop/` directory):

   ```sh
   npm install
   npm start
   ```

The Electron window opens the dashboard. Go to **Account Provisioning →
Provision**; in Electron the embedded webview appears with the autofill panel.

## Per-account isolation & correct OAuth binding

Each account's webview uses `partition="persist:acct_<id>"` — a fully isolated
browser session (own cookies/localStorage). Sign-up logs that partition in as
that account only; running the OAuth consent in the SAME partition makes the
token bind to that account, structurally. The Phase-1 duplicate-binding guard in
the backend is the belt-and-suspenders safety net.

## Manual validation that remains

Live Electron needs a GUI and live X, so the following must be done by an
operator: run **one real signup** against live X (solve the Arkose CAPTCHA),
confirm the fields autofill, then click **Continue → connect** and verify the
new account shows a verified `@handle`. If X gates the webview, the standalone
`provisioning-extension/` (100% real Chrome) is the fallback.

# Plan: Electron Webview Provisioning (auto-fill signup) + Per-Account Partitions

> Phase 2 (after the OAuth binding fix). Goal: an embedded webview in the dashboard that
> starts on the X signup page, auto-detects fields, and autofills everything from the
> backend. The operator only clicks Next and solves the CAPTCHA — zero data entry. Each
> account runs in its own isolated session partition, which also makes OAuth bind correctly.

## Why an Electron webview (not an iframe)
A plain `<iframe src="x.com">` renders blank — X sends `X-Frame-Options`/`frame-ancestors 'none'`.
An Electron `<webview>`/BrowserView is a separate Chromium guest (not an in-page iframe), so the
framing block doesn't apply and x.com loads. Tauri's webview is an equivalent alternative.

## Session partitions = the isolation mechanism (and the binding fix)
A `session.fromPartition('persist:acct_<id>')` is a fully isolated browser session (own cookies,
localStorage, cache), walled off from every other partition and from the operator's normal Chrome.
- Sign up for account A in `persist:acct_A` → that partition is logged in as **A only** (nothing
  pre-logged-in to bleed in).
- Run the OAuth connect **in the same partition** → consent authorizes A → token binds to A.
- Different account → different partition → different isolated login → correct binding, structurally.
This is why it fixes the "all post to one account" bug at the source; the Phase-1 duplicate-binding
guard is the belt-and-suspenders net.

## Architecture
```
Electron main process
 ├─ BrowserWindow → loads the dashboard (http://localhost:3000)  [webPreferences.webviewTag=true]
 │    └─ React Provision page renders:
 │         <webview partition="persist:acct_<id>" src="x.com/i/flow/signup" preload=autofill-preload.js>
 │              └─ autofill-preload.js (inside the webview)
 │                   • watch navigation (right URL?) + DOM (MutationObserver: field appeared?)
 │                   • on field → IPC to main → backend data → React-safe fill
 │                   • operator clicks Next / solves CAPTCHA
 └─ IPC handler: fetch backend /provisioning/{id}/* and /oauth/* (holds agent token; avoids CORS)
```

## Files (new `desktop/` dir + one frontend component)
- `desktop/main.js` — Electron main: window loads dashboard; `webviewTag=true`; per-account partition + preload registration; IPC bridge to backend holding `PROVISIONING_AGENT_TOKEN`.
- `desktop/autofill-preload.js` — webview preload: URL detection + `MutationObserver` field detection + React-safe fill (set value via native setter + dispatch input/change). **Reuse `provisioning-extension/content.js` logic + selectors.** Talks to main via IPC (no direct fetch → no CORS; token stays in main).
- `desktop/package.json` + electron-builder config.
- `frontend/src/features/provisioning/SignupWebview.tsx` — React (Electron-only) component rendering the `<webview>` with `persist:acct_<id>`, status, and a Continue/Connect control. Hidden when not in Electron (`window.process?.versions?.electron`).
- Backend: NO new endpoints — reuse `/provisioning/{id}/job|email-code|phone|phone-code`, `/oauth/x/authorize`, `/oauth/x/status` (+ Phase-1 changes).

## Flow
1. Click New Account → `<SignupWebview accountId partition="persist:acct_<id>">` at signup URL.
2. Preload fills email + generated password + name from `/job`; at the code step fills from `/email-code` (or `/phone-code`).
3. Operator clicks Next + solves Arkose CAPTCHA in the webview.
4. On signup success, navigate the SAME partition to the OAuth authorize URL → consent authorizes this new account → backend exchange (identity-verified, Phase-1) → bound correctly.
5. Card shows the new account with verified `@handle` + X-profile link.

## Per-account credential routing (posting to its own account)
- API posting already routes by `account_id` → `oauth-tokens/{account_id}` token. The Phase-1 binding fix guarantees that token is the account's own X user.
- Browser engagement uses per-account session cookies (`AccountSecrets/{account_id}`) + the `persist:acct_<id>` partition.
- No new "directory" — existing account_id-keyed storage + Electron partitions ARE the routing. Each account acts only with its own credentials.

## Risks / validation
- **Detection:** Electron webview = real Chromium + residential IP + human CAPTCHA → far better than the Playwright agent (which got the gated splash), but injected preload + webview props can still be fingerprinted. **Validate with one real signup before fleet use.** The standalone `provisioning-extension/` (100% real Chrome) is the fallback if X gates the webview.
- **Selectors** stay heuristic (`autocomplete=email`, `name=name|password`, `one-time-code`, `autocomplete=tel`); refine against live DOM via the existing screenshot/DOM debug-capture approach.
- **Packaging:** dashboard + backend stay Dockerized; Electron is a thin host on the operator machine pointing at localhost:3000/8000. Runtime/posting unchanged.

## Build order
1. Electron shell loads the dashboard (smoke test). 2. SignupWebview component + per-account partition renders x.com signup. 3. autofill-preload (port extension logic) + IPC backend bridge. 4. Auto-connect OAuth in the same partition. 5. One real validation run with the operator (live X + CAPTCHA).

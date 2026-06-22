# Plan: Fix OAuth Per-Account Binding + Account-Card X-Profile Link

> Phase 1 of the provisioning rework. Goal: every dashboard account posts to its **own** X
> account, never another's. Plus a clickable link on the account card to the real X profile.

## 1. Root cause
The acting X user at post time is decided **solely by the OAuth2 access token** stored at
`oauth-tokens/{account_id}`; `account_id` is never sent to X. The consent URL is
account-agnostic and `save_token` has **no uniqueness check on `x_user_id`**, so approving
consent while logged into one X user binds every account to it. It is **not** the app
credentials. (Current state: 3 accounts all map to `x_user_id 2054643922534875136`, all
stored with `x_user_id = null`.)

## 2. Confirmed bugs (verified in code)
- **B1** No uniqueness binding `x_user_id`→one account. `oauth_token_repository.py:29`; `twitter_oauth2_service.py:252`. High.
- **B2** Manual dashboard connect does zero identity verification. `oauth.py:48-117`. High.
- **B3** `x_user_id` best-effort, frequently null (errors swallowed) → defeats the guard. `twitter_oauth2_service.py:272-288`. High.
- **B4** Refresh never re-captures id → null stays null forever. `twitter_oauth2_service.py:326-349`. High.
- **B5** Connected username never captured/stored (no `user.fields=username`, no field). `oauth_token.py`; `oauth.py:120`. High.
- **B6** Callback drops identity — can't see which real account got bound. `oauth.py:109`; `OAuthRedirectHandler.tsx`. Med.
- **B7** Scan-then-write guard has a TOCTOU race; `list_tokens()` eventually-consistent. `ravendb_http.py:103`; `oauth_token_repository.py:40`. Med.
- **B8** Two unreconciled id sources (token vs `provisioning.x_user_id`); agent compares wrong one. `provisioning.py:109`; `oauth_connect.py:79`. Med.
- **B9** Posting path identity-blind — duplicates double-post until migration. `twitter_service.py:147`. Med.
- **B10** Card renders `twitter_handle` as plain unverified text; no id/username in scope. `AccountCard.tsx:84`. High (for link).

## 3. Fix — file by file

### Backend
- `app/models/oauth_token.py` — add `x_username: str | None = None` (null default → zero read migration; `model_dump(exclude_none=True)` + `model_validate` make it safe).
- `app/services/twitter_oauth2_service.py`:
  - Replace `_fetch_x_user_id` with `_resolve_identity(access_token) -> tuple[str|None,str|None]` calling `GET https://api.x.com/2/users/me?user.fields=username` → `(data.id, data.username)`. Bounded retry (2-3 on 429/5xx/network) so a flake doesn't silently null out.
  - `_store_token_response(account_id, payload, *, x_user_id=None, x_username=None)` — persist both; update both callers.
  - **Duplicate guard in `exchange_authorization_code`** (the ONE chokepoint both manual + agent flows hit). After resolving identity, before storing: if `x_uid` non-null and already bound to a DIFFERENT account_id → raise `ValueError` naming the conflict + `@handle`. Allow same-account reconnect. If `x_uid` null → store but mark `unverified`, never treat as unique. Delete the OAuth session in `try/finally`.
  - **Atomic binding sentinel** to close TOCTOU (B7): claim `oauth-bindings/{x_user_id}` create-if-absent; reject if a different account_id holds it.
  - `refresh_account_tokens` — pass BOTH `x_user_id` and `x_username` (else `exclude_none` drops username); **self-heal**: if id/username null after refresh, call `_resolve_identity` and persist.
  - `OAuthConnectionStatus` + `connection_status` — add `x_username`; tighten `is_connected` so connected implies a decryptable token; surface a `connected-unverified` signal when id is null.
  - Canonical identity = `OAuthTokenDocument.x_user_id` (treat `provisioning.x_user_id` advisory).
- `app/services/oauth_token_repository.py` — `find_account_by_x_user_id(x_user_id)`; sentinel `claim_binding(x_user_id, account_id)` / `release_binding(x_user_id)`; release on `delete_token`/disconnect.
- `app/infrastructure/ravendb_http.py` — additive `if_none_match`/empty-change-vector PUT for create-if-absent sentinel.
- `app/api/routes/oauth.py` — callback success redirect carries `x_username` (+ `unverified=1` when null); duplicate-rejection routes through existing `oauth_error` redirect with an actionable message; `/oauth/x/status` returns `x_username` + unverified.
- `app/api/routes/provisioning.py` — `oauth_status_for_agent` returns `x_username` too. (Guard stays in `exchange_authorization_code`.)
- `app/services/ravendb_service.py` — `_account_public` includes `x_user_id` + `x_username` (from `connection_status`) so the card needs no extra fetch. No token material exposed.
- (Optional, B9) `app/services/twitter_service.py` — when both `provisioning.x_user_id` and `token.x_user_id` non-null and disagree → log/alert, do NOT block.

### Frontend
- `frontend/src/types/domain/account.ts` — `OAuthStatus.x_username?`; `AccountSummary.x_user_id?` + `x_username?`.
- `frontend/src/lib/format.ts` — `buildXProfileUrl({xUsername,xUserId})`: prefer `https://x.com/i/user/${encodeURIComponent(xUserId)}` (immune to username changes); else validated `https://x.com/${username}` (`/^[A-Za-z0-9_]{1,15}$/`, trim, strip leading `@`); else `null`. Never build from `twitter_handle`; never interpolate null.
- `frontend/src/components/AccountCard.tsx` — render link via state machine: notProvisioned / notConnected / connectedNoIdentity / connectedVerified (→ `<a target="_blank" rel="noopener noreferrer">`). Show verified `x_username`; if it differs from editable `twitter_handle`, show both + mark handle unverified.
- `frontend/src/features/operations/OAuthStatusCard.tsx` + `frontend/src/features/account/AccountHqComponents.tsx` — same link where oauth status is already in scope; hide when id null.
- `frontend/src/app/OAuthRedirectHandler.tsx` — read `x_username`/`unverified`; toast "Connected as @{username} for {accountId}".

## 4. Cleanup + migration
- New `backend/scripts/backfill_oauth_identity.py` (model on `migrate_oauth_tokens_from_accounts.py`): `--dry-run` default; load all tokens; per null-id token decrypt → (refresh if expired) → `users/me?user.fields=username` → set id+username. Never delete; on decrypt fail / suspended / 401 → mark unresolved. **Detect collision groups** (x_user_id → [account_id]); print, refuse to auto-pick a survivor.
- Sequenced disconnect: land guard → dry-run → choose survivor → `disconnect(loser)` (deletes token + releases sentinel) + blank loser's `provisioning.x_user_id`/handle → reconnect each loser in an isolated session as its own X user.

## 5. Edge cases
users/me fail at exchange → null id, flag unverified, don't claim unique. Null-id duplicate vs new real-id → backfill before trusting guard. Concurrent connects → sentinel. `list_tokens()` skip = "cannot prove unique", not unique. Refresh must preserve username + self-heal null. Same-account reconnect allowed. Wrong-but-unique user → only visible via surfaced handle. Migration: won't-decrypt→skip; expired+refresh→refresh then resolve; suspended→unresolved. Frontend: blank/`@`/whitespace/URL handle → no href; null id while connected → "link unavailable", never `i/user/null`; expired → no live link; username change → href uses `i/user/{id}`. All external anchors `x.com` + `rel="noopener noreferrer"`.

## 6. Tests / verification
Backend unit (`backend/tests/unit/`, MagicMock repos + monkeypatch + httpx mocks): resolve_identity id+username (+url has user.fields); retry-then-null; exchange stores both; **reject duplicate x_user_id**; allow same-account reconnect; null-id not unique; refresh preserves username; refresh self-heals; sentinel blocks concurrent; status exposes username+unverified; callback redirect carries username + actionable rejection. Frontend: `format.test.ts` for buildXProfileUrl edges; AccountCard renders safe `<a>` only in verified state.
Manual E2E: connect A as U1 ✓; connect B still as U1 → rejected; connect B as U2 → distinct id; assert no x_user_id maps to >1 account; post from A and B → each lands on its own account.

## 7. Rollout order
1. Additive capture (x_username field, _resolve_identity, refresh preserve+self-heal, status). 2. Guard + sentinel. 3. API surfacing. 4. Frontend link. 5. Backfill dry-run → survivor → disconnect+reconnect. 6. Verify.

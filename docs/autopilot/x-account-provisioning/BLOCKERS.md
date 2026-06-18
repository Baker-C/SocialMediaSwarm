# Blockers — X Account Provisioning

## 1. Disposable email/phone providers not configured (unit 6) — EXTERNAL, route-around in place
- **Attempted:** built `DisposableEmailClient` + `DisposablePhoneClient` with httpx + provider-behind-one-private-method, all covered by httpx-patch unit tests (13 passed).
- **Why blocked:** no owned email domain + Cloudflare catch-all/mailbox-read API is provisioned, and no SIM-based OTP provider account exists. X (2026) rejects VoIP/Twilio, so a SIM-tier provider is required.
- **Route-around:** clients are fully built and tested against assumed JSON contracts; providers are configurable via `.env` (`disposable_email_*`, `disposable_phone_*`).
- **Remains:** create/own the email domain + mailbox read API; sign up a SIM OTP provider; reconcile `_fetch_messages` / `_provider_*` request shapes to the chosen providers. Needs real credentials only.

## 2. Agent signup selectors are placeholders (unit 8) — EXTERNAL (spike), route-around in place
- **Attempted:** full agent package (`BrowserPort`, `PageDetector`, 12 handlers, orchestrator) with all logic unit-tested via fakes (37 passed), Playwright import kept lazy.
- **Why blocked:** X serves a single reactive, obfuscated, frequently-changing signup DOM; real selectors cannot be known without a manual spike against the live flow (plan `09 §1`).
- **Route-around:** all selectors centralized in `agent/selectors.py`, clearly marked `# PLACEHOLDER`; decision logic, loop bounds, CAPTCHA pause/resume, handler behavior complete and tested.
- **Remains:** run the manual spike, fill `selectors.py` + the `TextSignals` tokens, then exercise against the live flow. Code-complete otherwise.

## 3. Pre-existing unrelated test failure — DEFERRED (out of scope)
- `tests/unit/test_act_artifacts_and_deps.py::test_artifacts_dict_has_16_entries` asserts `len(ARTIFACTS)==16` but it is 19.
- **Cause:** the already-merged Seedance/Seedream media tools (commit 098f0ee on `main`) added MediaRef artifacts; this assertion was not updated then. **Not caused by and not in scope of provisioning** (provisioning added zero ArtifactKeys).
- **Deferred:** fixing belongs to the media-tools owner, not this feature. Flagged so it isn't mistaken for a regression.

## 4. Frontend test discovery in this worktree path — DEFERRED (environmental)
- `react-scripts test` auto-discovery finds 0 tests because the worktree path contains `\.claude\`, and micromatch reads `\.` as an escape in the generated `testMatch` glob — affects ALL frontend tests, pre-existing ones included.
- **Route-around:** ran with explicit `--testMatch="**/*.test.tsx" --testMatch="**/*.test.ts"` → new Jest tests pass (8 passed).
- **Deferred:** environmental to this checkout path; a normal CI checkout (no `.claude` segment) is unaffected.

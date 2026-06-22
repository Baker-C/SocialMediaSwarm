# X Provisioning Autofill (browser extension)

Human-driven signup with autofill. You open X in your **own** Chrome, navigate the
signup yourself, and solve the CAPTCHA. A floating panel fills each field with the
account's throwaway data + verification codes pulled from the provisioning backend.
Because it's your real browser/profile, X sees a normal human — no automation gating.

## Load it (once)
1. Chrome → `chrome://extensions`
2. Toggle **Developer mode** (top-right) on.
3. **Load unpacked** → select this `provisioning-extension/` folder.

## Configure (once per session)
Click the extension icon → set:
- **Backend URL**: `http://localhost:8000/api`
- **Agent token**: the `PROVISIONING_AGENT_TOKEN` from `backend/.env`
- **Account ID**: the draft account you're provisioning (e.g. `spike_test_1`)
- **Save**

## Use it
1. Create the draft account first (dashboard, or `scripts/add_account.py`).
2. Go to `https://x.com` and start "Create account" yourself.
3. On each step, click the matching panel button:
   - **Fill name / Fill email** — from the account spec
   - **Gen + fill password** — generates a strong password, fills it, copies it to your clipboard (save it!)
   - **Get email code + fill** — pulls the latest email OTP from the backend
   - **Acquire phone + fill** / **Get SMS code + fill** — only if X asks for a phone
4. You click Next / submit / solve CAPTCHA. The extension never navigates or submits.

## Notes
- Field selectors are heuristics (`name`/`autocomplete`/`type`); if a fill misses,
  the panel status shows the value so you can paste it manually.
- Email/SMS codes only arrive once the backend's n8n email (Mailgun) and phone
  (TextVerified) workflows are wired to real providers.
- The password is shown/copied but not yet persisted server-side — save it.

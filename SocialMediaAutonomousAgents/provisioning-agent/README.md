# Provisioning Agent

Local Playwright + real-Chrome agent that drives the X signup/dev-app flow on the
**operator's machine**. The hosted backend brokers the job and stores the result; this
package holds no persistence and no provider secrets.

## Design

All decision logic (page-state machine, handlers, orchestrator) depends only on the
`BrowserPort` protocol, so it is unit-tested with a scripted fake browser and a fake
backend client — **no real Chrome, no network in tests**. Playwright is imported lazily
inside `PlaywrightBrowser.__init__` only, so the rest of the package imports without
Playwright installed.

> The selectors in `agent/selectors.py` are **placeholders**. The real values must be
> captured from a manual DOM spike (`docs/plans/x-account-provisioning/09 §1`) before the
> agent can drive the live flow.

## Install

```bash
pip install -r requirements.txt
playwright install chromium   # the real run uses channel="chrome"; this seeds the browser bits
```

## Run

```bash
export BACKEND_URL=https://your-backend.example
export PROVISIONING_AGENT_TOKEN=...        # shared secret from backend config
export CHROME_PROFILE_DIR=C:\path\to\profile
export ACCOUNT_ID=acc_123
python -m agent.run
```

## Test

```bash
cd provisioning-agent
python -m pytest -q          # runs WITHOUT playwright installed
```

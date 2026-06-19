# 06 — Local Provisioning Agent (Playwright + real Chrome)

**New package:** `SocialMediaAutonomousAgents/provisioning-agent/` — runs on the **operator's
machine**, not in the hosted backend. Has its **own `requirements.txt`** (Playwright lives here only).

This is the only component exposed to X's live defenses. Its design goal: **all decision logic is
pure and unit-testable behind a `BrowserPort` protocol**, so the page-state machine and handlers are
tested with a scripted fake browser and a fake backend client — no real Chrome, no network in tests.

> **Build this LAST and only after the spike (`09 §1`).** The page-state machine must be built against
> the *real* X DOM captured in the spike, not guessed.

## 1. Package layout

```
provisioning-agent/
  requirements.txt            # playwright, httpx, pydantic
  README.md                   # install: pip install -r ...; playwright install chromium
  agent/
    __init__.py
    config.py                 # AGENT env: BACKEND_URL, PROVISIONING_AGENT_TOKEN, CHROME_PROFILE_DIR, ACCOUNT_ID
    backend_client.py         # typed httpx client for the 05 agent routes
    browser_port.py           # BrowserPort protocol + PlaywrightBrowser impl
    page_state.py             # PageState enum + PageDetector
    handlers/
      __init__.py             # HANDLERS registry (ordered)
      base.py                 # Handler protocol + HandlerResult
      email_entry.py  password.py  name_handle.py  email_verify.py
      phone_entry.py  phone_verify.py  profile_setup.py
      dev_app.py  dev_agreement.py  billing.py  key_capture.py
      captcha.py              # detect-only; signals pause
    orchestrator.py           # the loop: detect -> dispatch -> report -> (pause on captcha)
    run.py                    # entrypoint: python -m agent.run  (reads config, drives one account)
  tests/
    test_page_detector.py  test_handlers.py  test_orchestrator.py
    fakes.py                  # FakeBrowser (scripted pages), FakeBackend
```

## 2. `BrowserPort` — the testability seam

A minimal protocol over the handful of Playwright operations the handlers use. Real impl wraps a
Playwright `Page`; the fake impl scripts a sequence of page snapshots.

```python
class BrowserPort(Protocol):
    def goto(self, url: str) -> None: ...
    def url(self) -> str: ...
    def exists(self, selector: str) -> bool: ...
    def text(self, selector: str) -> str: ...           # "" if absent
    def fill(self, selector: str, value: str) -> None: ...
    def click(self, selector: str) -> None: ...
    def upload(self, selector: str, data: bytes, filename: str) -> None: ...
    def wait_for(self, selector: str, timeout_ms: int = 15000) -> bool: ...
    def storage_state(self) -> str: ...                  # JSON cookies/localStorage -> session_cookies

class PlaywrightBrowser:
    """Wraps a persistent-context real Chrome. Stealth patches applied here."""
    def __init__(self, profile_dir: str) -> None: ...
    # launch_persistent_context(profile_dir, headless=False, channel="chrome")
```

Real Chrome, persistent profile, `headless=False`, `channel="chrome"` (uses the operator's installed
Chrome — best fingerprint). Apply `playwright-stealth` / rebrowser patches in this class only.

## 3. `PageState` + `PageDetector`

```python
class PageState(str, Enum):
    EMAIL_ENTRY="email_entry"; PASSWORD="password"; NAME_HANDLE="name_handle"
    EMAIL_VERIFY="email_verify"; PHONE_ENTRY="phone_entry"; PHONE_VERIFY="phone_verify"
    PROFILE_SETUP="profile_setup"; DEV_APP="dev_app"; DEV_AGREEMENT="dev_agreement"
    BILLING="billing"; KEY_CAPTURE="key_capture"; CAPTCHA="captcha"
    SUCCESS="success"; UNKNOWN="unknown"
```

`PageDetector.detect(b: BrowserPort) -> PageState` uses **selector + visible-text signals**, ordered so
CAPTCHA is checked first (it can overlay any page):

```python
def detect(self, b: BrowserPort) -> PageState:
    if b.exists(SEL.captcha_iframe) or "arkose" in b.text("body").lower(): return PageState.CAPTCHA
    for state, probe in SIGNALS:        # SIGNALS: ordered list of (PageState, lambda b: bool)
        if probe(b): return state
    return PageState.UNKNOWN
```

All selectors live in **one `selectors.py`** captured from the spike (`09 §1`) — when X changes its
DOM, this is the single file to update. X signup is a single reactive flow, so detection is
DOM-state-based, not URL-based.

## 4. Handler protocol

```python
@dataclass
class HandlerResult:
    advanced: bool = True          # took an action and expects the page to change
    needs_user: bool = False       # pause (CAPTCHA)
    failed: bool = False; error: str | None = None
    status_note: str | None = None # pushed to backend step_log

class Handler(Protocol):
    state: PageState
    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult: ...
```

`AgentContext` carries the backend client (for lazy disposable-phone creation + OTP fetch), the
media bytes (avatar/header, fetched once), and the job. Handlers are small and pure-ish:

- **email_entry:** fill `job.email`, click next.
- **password:** generate a strong password (store on ctx → returned in result), fill, next.
- **name_handle:** fill `job.display_name` + `job.handle`; on "handle taken" (detect inline error)
  ask backend for an alternate (or append a digit) and retry — bounded retries.
- **email_verify:** poll `ctx.backend.fetch_email_code()` (07) → fill → next.
- **phone_entry (conditional):** lazily `ctx.backend.create_phone()` (07), fill, next.
- **phone_verify:** poll `ctx.backend.fetch_sms_code()` → fill → next.
- **profile_setup:** `b.upload(avatar_selector, avatar_bytes,...)`, header upload, fill bio, save.
- **dev_app / dev_agreement:** create app, accept agreement.
- **billing:** if `job.card` present, fill card fields; else skip (free-tier path).
- **key_capture:** read API key/secret/bearer from the page → `ctx.result.dev_* = ...`.
- **captcha:** `return HandlerResult(needs_user=True, status_note="awaiting CAPTCHA")` — no action.

Handlers register in an ordered `HANDLERS: dict[PageState, Handler]`.

## 5. Orchestrator loop

```python
def run_provisioning(b, job, ctx) -> ProvisioningResult:
    ctx.backend.push_status(status="in_progress", current_page="start")
    b.goto(X_SIGNUP_URL)
    deadline = ...
    while now() < deadline:
        state = detector.detect(b)
        ctx.backend.push_status(status=_map(state), current_page=state.value)
        if state == PageState.SUCCESS: break
        if state == PageState.CAPTCHA:
            ctx.backend.push_status(status="awaiting_captcha", current_page="captcha")
            _wait_for_continue(ctx.backend)          # poll GET control until "continue"/"cancel"
            continue                                  # re-detect after the operator solved it
        handler = HANDLERS.get(state)
        if handler is None:                           # UNKNOWN: short wait + re-detect, bounded
            if not _settle(b): _fail(ctx, "stuck on unknown page"); break
            continue
        res = handler.handle(b, job, ctx)
        if res.status_note: ctx.backend.push_status(status=_map(state), current_page=state.value, note=res.status_note)
        if res.failed: _fail(ctx, res.error); break
        b_settle()                                    # wait for navigation/render
    ctx.result.session_cookies = b.storage_state()
    return ctx.result
```

Key properties:
- **CAPTCHA is a re-enterable state**, not a one-shot — it can recur; each time we pause + wait + re-detect.
- **Idempotent-ish:** every loop re-detects, so a missed click or unexpected interstitial self-corrects.
- **Bounded:** overall deadline + bounded UNKNOWN settle attempts + bounded handle-retry → never hangs.
- On completion the agent POSTs `ctx.result` to `/result` (05); backend encrypts + stores.

`run.py` wires real `PlaywrightBrowser` + `BackendClient`, fetches the job, fetches avatar/header
bytes, runs the loop, posts the result; on exception pushes `status="failed"`.

## 6. Backend client (`backend_client.py`)

Typed httpx wrapper over the `05` agent routes; presents `Authorization: Bearer <PROVISIONING_AGENT_TOKEN>`:
`fetch_job()`, `push_status(...)`, `poll_control()`, `post_result(r)`, plus disposable helpers it
proxies through the backend: `fetch_email_code()`, `create_phone()`, `fetch_sms_code()` (these hit
`07` endpoints; keeps provider keys in the backend, not on the operator machine).

## 7. Why this is clean & modular
- **One selector file** = one place to fix when X changes.
- **Handlers are independent** = add/replace a page without touching others.
- **`BrowserPort`** = logic tested without a browser; Playwright confined to one class.
- **Backend-broker** = no inbound port, no CORS, no provider secrets on the operator box.
- **Agent holds no persistence** = backend owns all state/secrets; agent is a stateless executor
  (and is the natural home for Scope 2 engagement later — same `BrowserPort`, new handlers).

## 8. Tests (`provisioning-agent/tests/`)
- **`fakes.py`:** `FakeBrowser` returns scripted `exists/text` per "page" and records `fill/click/upload`;
  advancing the script when a handler "clicks next". `FakeBackend` records `push_status`, returns a
  canned job, scripts `poll_control` to return `"continue"` after N polls, captures `post_result`.
- **`test_page_detector.py`:** feed DOM snapshots (from the spike) → assert the expected `PageState`,
  incl. CAPTCHA-overlay precedence.
- **`test_handlers.py`:** each handler against a `FakeBrowser` → asserts the right fields filled / file
  uploaded / result populated; handle-taken retry path; billing-skip when `job.card is None`.
- **`test_orchestrator.py`:** scripted multi-page run incl. a CAPTCHA pause that resolves on the Nth
  control poll → asserts terminal `post_result` with cookies + dev keys, and the status sequence.

## Done when
- `python -m agent.run` provisions against the spike-captured flow (or a staging double): detects pages,
  fills/clicks, pauses + resumes on CAPTCHA, uploads images, captures keys, posts an encrypted result.
- All agent logic unit-tested via fakes; Playwright isolated to `PlaywrightBrowser`.
- Selectors centralized; backend holds all secrets/state.

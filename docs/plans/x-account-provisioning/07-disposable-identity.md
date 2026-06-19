# 07 — Disposable Identity: email + SIM-phone clients

**Touches:** `backend/app/infrastructure/disposable_email_client.py` (new),
`backend/app/infrastructure/disposable_phone_client.py` (new), `backend/app/api/routes/provisioning.py`
(agent endpoints), `config.py`, `.env.example`

These live in the **backend** so provider API keys never reach the operator machine — the agent
proxies through the backend (`06 §6`). Both follow the repo's HTTP-client conventions: `import httpx`,
sync `httpx.Client`, config via `settings.*`, testable by patching `httpx.Client`
(`test_twitter_oauth2_service.py:121` pattern).

## 1. Email — owned domain + Cloudflare Email Routing (recommended)

Public disposable domains are blocklisted by X. Most reliable: a **domain you own** with Cloudflare
Email Routing catch-all forwarding into a mailbox/API you can read. The client exposes:

```python
class DisposableEmailClient:
    def __init__(self, client: httpx.Client | None = None) -> None: ...
    def create_inbox(self, account_id: str) -> str:
        """Return a fresh address on the owned domain, e.g. f'{slug}-{rand}@{settings.disposable_email_domain}'.
        With catch-all routing, 'creating' is just minting an address; no API call needed."""
    def fetch_code(self, address: str, *, timeout_s: int = 180, pattern: str = r"\b\d{6}\b") -> str | None:
        """Poll the mailbox API for the latest message to `address`; regex the verification code."""
```

The `fetch_code` backend (how mail is read) depends on the mailbox: Cloudflare Worker → KV, IMAP, or a
provider API (mail.tm as a fallback provider). Abstract the read behind one private method so the
provider can change without touching callers.

> **Fallback provider:** `mail.tm` has a free JSON API (create account, poll messages) — usable as a
> secondary if the owned-domain path isn't ready. Same `create_inbox`/`fetch_code` surface.

## 2. Phone — SIM-based OTP service (conditional)

VoIP/Twilio is blocked by X (2026). Use a **SIM-based** OTP-receive provider (5sim SIM tier /
TextVerified / similar). Numbers cost per-use, so the agent only requests one when a phone page
actually appears.

```python
class DisposablePhoneClient:
    def __init__(self, client: httpx.Client | None = None) -> None: ...
    def acquire_number(self, *, service: str = "twitter", country: str | None = None) -> PhoneLease:
        """Buy/lease a number for X; returns {id, phone}. Raises if none available."""
    def fetch_code(self, lease_id: str, *, timeout_s: int = 240, pattern: str = r"\b\d{6}\b") -> str | None:
        """Poll the provider for the SMS to this lease; regex the code."""
    def release(self, lease_id: str) -> None: ...
```

Provider is pluggable behind this interface (one `_provider` impl). Log acquire/verify failures with
the provider's reason — phone acceptance is the most variable step.

## 3. Agent-facing endpoints (in `provisioning.py`, agent-token gated)

The agent proxies disposable ops through the backend:

```python
@agent_router.get("/provisioning/{account_id}/email-code")    # -> {"code": "123456" | null}
@agent_router.post("/provisioning/{account_id}/phone")        # -> {"phone": "+1...", "lease_id": "..."} ; stores phone in AccountSecrets
@agent_router.get("/provisioning/{account_id}/phone-code")    # -> {"code": "654321" | null}
```

`email-code` reads the stored `disposable_email` from `AccountSecrets` and calls `fetch_code`.
`phone` calls `acquire_number`, persists the number via `AccountSecretsService.upsert(...,
disposable_phone=...)`, and returns it. `phone-code` polls by stored lease.

## 4. Config — `config.py` + `.env.example`

```python
# --- Disposable identity ---
disposable_email_domain: str = ""           # owned domain for catch-all addresses
disposable_email_api_base: str = ""         # mailbox read API (worker/imap-bridge/mail.tm)
disposable_email_api_key: str = ""
disposable_phone_api_base: str = ""         # SIM OTP provider
disposable_phone_api_key: str = ""
disposable_phone_country: str = ""          # optional default
```

Mirror as commented entries in `.env.example` with a header explaining the SIM-vs-VoIP requirement.

## 5. Tests (`tests/unit/test_disposable_clients.py`)

Client-layer tests using the `httpx.Client` patch + real `httpx.Response` fixtures:
- `create_inbox` returns an `@{domain}` address; deterministic enough to assert the domain suffix
  (seed the random part via an injected callable, or just assert the suffix/shape).
- `fetch_code` parses a 6-digit code from a canned message payload; returns `None` on no-match/timeout
  (use a `side_effect` list of responses to simulate polling, like `test_x_client_oauth2.py:99-106`).
- `acquire_number` returns `{id, phone}`; maps a provider error response to a raised exception.
- Endpoint tests: agent-token gate (401 without token), `phone` persists the number via a fake
  `AccountSecretsService`, `email-code` returns the parsed code.

Keep everything **synchronous** (no `AsyncClient`) — the repo has no async test runner.

## Done when
- Both clients exist behind clean interfaces with pluggable providers; keys only in backend config.
- Agent endpoints proxy email/phone code retrieval and number acquisition (agent-token gated).
- Code-parsing + polling + error mapping covered by `httpx.Client`-patch tests.

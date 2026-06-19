# 05 — Provisioning Routes & Orchestration

**Touches:** `backend/app/api/routes/provisioning.py` (new), `provisioning_types.py` (new),
`backend/app/services/provisioning_service.py` (new), `backend/app/main.py`, `backend/app/core/config.py`

The backend is the **broker + store** between the dashboard and the local agent (`00 §4`). It owns no
browser. It exposes: frontend-facing control/status (auth-gated) and agent-facing job/status/result
(agent-token-gated). State is the `AccountProvisioning` sub-doc (`01`) for progress + `AccountSecrets`
(`02`) for outcomes.

## 1. Service — `provisioning_service.py`

Thin orchestration over the repos; pure enough to unit-test with injected fakes.

```python
class ProvisioningService:
    def __init__(self, repo: AccountRepository | None = None,
                 secrets: AccountSecretsService | None = None) -> None:
        self.repo = repo or AccountRepository()
        self.secrets = secrets or AccountSecretsService()

    def start(self, account_id: str) -> None:
        acc = self.repo.load(account_id)
        if acc is None: raise LookupError(account_id)
        if acc.provisioning.status not in ("draft", "failed", "cancelled"):
            raise ValueError(f"already provisioning (status={acc.provisioning.status})")
        acc.provisioning.status = "in_progress"
        acc.provisioning.attempt_count += 1
        acc.provisioning.error_message = None
        acc.provisioning.started_at = <iso>            # stamped at call site
        self.repo.save(acc)

    def update_status(self, account_id: str, *, status: str, current_page: str = "",
                      note: str | None = None, x_user_id: str = "", dev_app_id: str = "") -> None:
        acc = self.repo.load(account_id)
        acc.provisioning.status = status
        if current_page: acc.provisioning.current_page = current_page
        if note: acc.provisioning.step_log.append(note)
        if x_user_id: acc.provisioning.x_user_id = x_user_id
        if dev_app_id: acc.provisioning.dev_app_id = dev_app_id
        self.repo.save(acc)

    def build_job(self, account_id: str) -> "ProvisioningJob":
        """Spec + disposable creds + card the agent needs. Generates/loads disposable creds lazily."""
        acc = self.repo.load(account_id)
        sec = self.secrets.get(account_id)
        email = sec.disposable_email if sec else None
        if not email:
            email = disposable_email_client().create_inbox(account_id)     # 07
            self.secrets.upsert(account_id, disposable_email=email)
        # phone is created lazily by the agent only when a phone page appears (07); not pre-issued here
        return ProvisioningJob(
            account_id=account_id, handle=acc.profile.twitter_handle,
            display_name=acc.provisioning.display_name, bio=acc.provisioning.bio,
            avatar_asset_id=acc.provisioning.images.avatar_asset_id,
            header_asset_id=acc.provisioning.images.header_asset_id,
            email=email,
            card=settings.provisioning_card.as_dict() if settings.provisioning_card else None,
        )

    def store_result(self, account_id: str, result: "ProvisioningResult") -> None:
        self.secrets.upsert(account_id,
            password=result.password, session_cookies=result.session_cookies,
            dev_api_key=result.dev_api_key, dev_api_secret=result.dev_api_secret,
            dev_bearer_token=result.dev_bearer_token, updated_at=<iso>)
        self.update_status(account_id, status="complete",
            x_user_id=result.x_user_id, dev_app_id=result.dev_app_id, note="provisioning complete")

    # control flag for the FunCaptcha pause (poll target for the agent)
    def set_control(self, account_id: str, action: str) -> None: ...   # store on provisioning (transient field) or a tiny ProvisioningControl doc
    def get_control(self, account_id: str) -> str | None: ...
```

> **Control flag storage:** simplest is a transient field on `AccountProvisioning`
> (`control_action: str = ""`, not persisted to any view). The frontend POST sets it `"continue"`/
> `"cancel"`; the agent polls `get_control`, consumes it (clears to `""`) and proceeds. Keep it off
> the public view.

## 2. Types — `provisioning_types.py`

```python
class ProvisioningJob(BaseModel):
    account_id: str; handle: str; display_name: str; bio: str
    avatar_asset_id: str | None; header_asset_id: str | None
    email: str
    card: dict | None = None        # {number, exp, cvv, name} from .env, only if configured

class ProvisioningResult(BaseModel):
    x_user_id: str = ""; dev_app_id: str = ""
    password: str | None = None; session_cookies: str | None = None
    dev_api_key: str | None = None; dev_api_secret: str | None = None; dev_bearer_token: str | None = None

class StatusUpdate(BaseModel):
    status: str; current_page: str = ""; note: str | None = None
    x_user_id: str = ""; dev_app_id: str = ""

class ControlBody(BaseModel):
    action: Literal["continue", "cancel"]

# SSE emit helpers for the frontend status stream
def emit_status(p: AccountProvisioning) -> dict: ...
def emit_done() -> dict: ...
def emit_error(msg: str) -> dict: ...
```

## 3. Routes — `provisioning.py`

Two auth surfaces. Frontend routes use the existing `require_auth` (applied at registration). Agent
routes use a separate `require_agent_token` dependency declared **per-route** (so they're not behind
the dashboard password):

```python
router = APIRouter()
svc = ProvisioningService()

def require_agent_token(authorization: str = Header(default="")) -> None:
    expected = settings.provisioning_agent_token
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="bad agent token")

# ---- frontend-facing (inherit router-group require_auth) ----
@router.post("/provisioning/{account_id}/start", status_code=202)
def start(account_id: str):
    try: svc.start(account_id)
    except LookupError: raise HTTPException(404, "account not found")
    except ValueError as e: raise HTTPException(409, str(e))
    return {"ok": True}

@router.get("/provisioning/{account_id}/status")           # SSE
async def status_stream(account_id: str, request: Request): ...   # worker tails provisioning.status

@router.post("/provisioning/{account_id}/control")
def control(account_id: str, body: ControlBody):
    svc.set_control(account_id, body.action); return {"ok": True}

# ---- agent-facing (override auth) ----
@router.get("/provisioning/{account_id}/job", dependencies=[Depends(require_agent_token)])
def job(account_id: str) -> ProvisioningJob: return svc.build_job(account_id)

@router.post("/provisioning/{account_id}/status", dependencies=[Depends(require_agent_token)])
def push_status(account_id: str, body: StatusUpdate):
    svc.update_status(account_id, status=body.status, current_page=body.current_page,
                      note=body.note, x_user_id=body.x_user_id, dev_app_id=body.dev_app_id)
    return {"ok": True}

@router.get("/provisioning/{account_id}/control", dependencies=[Depends(require_agent_token)])
def poll_control(account_id: str) -> dict:
    return {"action": svc.get_control(account_id) or ""}

@router.post("/provisioning/{account_id}/result", dependencies=[Depends(require_agent_token)])
def result(account_id: str, body: ProvisioningResult):
    svc.store_result(account_id, body); return {"ok": True}
```

> **Auth nuance:** the agent routes live on the same router, which is registered under
> `dependencies=_auth`. To let the agent in *without* the dashboard token, either (a) put agent routes
> on a **second router** registered *without* `_auth` but each route carrying
> `Depends(require_agent_token)`, or (b) make `require_auth` accept the agent token too. **Choose (a)** —
> it keeps the two trust domains explicit. So: `provisioning.router` (frontend, `_auth`) +
> `provisioning_agent.router` (agent-token only), both in `provisioning.py`.

## 4. SSE status stream

Reuse the worker/queue pattern (`force_post.py:42-91`). The worker loops: read
`acc.provisioning`, `emit_status(...)`, sleep a short interval, repeat until status in
`{complete, failed, cancelled}` then `emit_done()`. (Short-poll of the doc is fine here; provisioning
is not high-frequency. If a NATS event already fires on provisioning changes, subscribe instead.)

## 5. Config — `config.py` + `.env.example`

Add a settings group (after the fal block, `config.py:131`):

```python
# --- Account provisioning ---
provisioning_agent_token: str = ""          # shared secret the local agent presents
provisioning_agent_enabled: bool = False
# pay-per-use card (single operator card; PCI risk accepted for throwaway use)
provisioning_card_number: str = ""
provisioning_card_exp: str = ""             # MM/YY
provisioning_card_cvv: str = ""
provisioning_card_name: str = ""
```

Add a `provisioning_card` convenience property returning a small object/dict when all fields are set,
else `None`. Mirror commented entries in `.env.example`. Disposable email/phone settings come in `07`.

## 6. Register routers

`main.py`: import `provisioning`; register `provisioning.router` under `dependencies=_auth` and
`provisioning.agent_router` (agent-token) **without** `_auth`.

## 7. Tests (`tests/unit/test_provisioning_routes.py`, `test_provisioning_service.py`)

- **Service:** inject fake `AccountRepository` + fake `AccountSecretsService`. `start` flips status to
  `in_progress` and bumps `attempt_count`; rejects when already in progress (409 path). `store_result`
  upserts secrets and sets status `complete` with `x_user_id`. `build_job` lazily creates an email when
  none stored (patch `disposable_email_client`).
- **Routes:** `TestClient` (auth auto-bypassed by `conftest`). Agent routes: without the agent token →
  401; with `monkeypatch.setattr(provisioning_routes.settings, "provisioning_agent_token", "t")` +
  `Authorization: Bearer t` → 200. `control` sets the flag; `poll_control` returns then clears it.
- **Card:** with card env unset, `build_job(...).card is None`; with all set, `card` is the dict.

## Done when
- Frontend can start/cancel and stream status; agent can fetch job, push status, poll control, post result.
- Two trust domains: dashboard `require_auth` vs `require_agent_token`, tested both ways.
- `store_result` lands secrets in `AccountSecrets` (encrypted) and flips status to `complete`.
- Config + `.env.example` updated; routers registered.

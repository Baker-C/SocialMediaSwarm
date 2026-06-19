"""Provisioning API: two trust domains on two routers.

`router` is registered under the dashboard `require_auth` gate (frontend-facing:
start, status SSE, control). `agent_router` is registered WITHOUT that gate; each
agent route carries `Depends(require_agent_token)` so the local agent authenticates
with its own shared secret instead of the dashboard password.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.routes.provisioning_types import (
    ControlBody,
    PhoneInputBody,
    ProvisioningJob,
    ProvisioningResult,
    StatusUpdate,
    emit_done,
    emit_error,
    emit_status,
)
from app.core.config import settings
from app.infrastructure.disposable_email_client import get_disposable_email_client
from app.infrastructure.disposable_phone_client import get_disposable_phone_client
from app.services.account_secrets_service import AccountSecretsService
from app.services.provisioning_service import ProvisioningService

router = APIRouter()
agent_router = APIRouter()
svc = ProvisioningService()
secrets_svc = AccountSecretsService()

# Transient phone leases keyed by account_id (lease ids are not persisted to AccountSecrets).
_phone_leases: dict[str, str] = {}

_TERMINAL = {"complete", "failed", "cancelled"}
_POLL_SECONDS = 2.0


def require_agent_token(authorization: str = Header(default="")) -> None:
    expected = settings.provisioning_agent_token
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="bad agent token")


# ── frontend-facing (inherit router-group require_auth) ──

@router.post("/provisioning/{account_id}/start", status_code=202)
def start(account_id: str):
    try:
        svc.start(account_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="account not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


async def _sse_status(account_id: str, request: Request):
    while True:
        if await request.is_disconnected():
            break
        acc = await asyncio.to_thread(svc.repo.load, account_id)
        if acc is None:
            yield f"data: {json.dumps(emit_error('account not found'))}\n\n"
            break
        yield f"data: {json.dumps(emit_status(acc.provisioning))}\n\n"
        if acc.provisioning.status in _TERMINAL:
            yield f"data: {json.dumps(emit_done())}\n\n"
            break
        await asyncio.sleep(_POLL_SECONDS)


@router.get("/provisioning/{account_id}/status")
async def status_stream(account_id: str, request: Request):
    return StreamingResponse(_sse_status(account_id, request), media_type="text/event-stream")


@router.post("/provisioning/{account_id}/control")
def control(account_id: str, body: ControlBody):
    svc.set_control(account_id, body.action)
    return {"ok": True}


@router.post("/provisioning/{account_id}/phone-input")
def phone_input(account_id: str, body: PhoneInputBody):
    """Operator provides phone number + verification code for manual OTP mode."""
    get_disposable_phone_client().set_manual_phone(body.lease_id, body.phone, body.code)
    return {"ok": True}


# ── agent-facing (override auth: agent-token only, per-route) ──

@agent_router.get("/provisioning/{account_id}/job", dependencies=[Depends(require_agent_token)])
def job(account_id: str) -> ProvisioningJob:
    try:
        return svc.build_job(account_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="account not found") from None


@agent_router.post("/provisioning/{account_id}/status", dependencies=[Depends(require_agent_token)])
def push_status(account_id: str, body: StatusUpdate):
    try:
        svc.update_status(
            account_id,
            status=body.status,
            current_page=body.current_page,
            note=body.note,
            x_user_id=body.x_user_id,
            dev_app_id=body.dev_app_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="account not found") from None
    return {"ok": True}


@agent_router.get("/provisioning/{account_id}/control", dependencies=[Depends(require_agent_token)])
def poll_control(account_id: str) -> dict:
    return {"action": svc.get_control(account_id) or ""}


@agent_router.post("/provisioning/{account_id}/result", dependencies=[Depends(require_agent_token)])
def result(account_id: str, body: ProvisioningResult):
    try:
        svc.store_result(account_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail="account not found") from None
    return {"ok": True}


# ── disposable identity (email + SIM-phone) proxied for the agent ──

@agent_router.get("/provisioning/{account_id}/email-code", dependencies=[Depends(require_agent_token)])
def email_code(account_id: str) -> dict:
    sec = secrets_svc.get(account_id)
    address = sec.disposable_email if sec else None
    if not address:
        raise HTTPException(status_code=409, detail="no disposable email for account")
    code = get_disposable_email_client().fetch_code(address)
    return {"code": code}


@agent_router.post("/provisioning/{account_id}/phone", dependencies=[Depends(require_agent_token)])
def phone(account_id: str) -> dict:
    lease = get_disposable_phone_client().acquire_number()
    secrets_svc.upsert(account_id, disposable_phone=lease.phone)
    _phone_leases[account_id] = lease.lease_id
    return {"phone": lease.phone, "lease_id": lease.lease_id}


@agent_router.get("/provisioning/{account_id}/phone-code", dependencies=[Depends(require_agent_token)])
def phone_code(account_id: str) -> dict:
    lease_id = _phone_leases.get(account_id)
    if not lease_id:
        raise HTTPException(status_code=409, detail="no phone lease for account")
    code = get_disposable_phone_client().fetch_code(lease_id)
    return {"code": code}

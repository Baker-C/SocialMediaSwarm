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
from app.services.twitter_oauth2_service import TwitterOAuth2Service
from pydantic import BaseModel

router = APIRouter()
agent_router = APIRouter()
svc = ProvisioningService()
secrets_svc = AccountSecretsService()
oauth_svc = TwitterOAuth2Service()


class PhoneAssignBody(BaseModel):
    phone: str


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


@agent_router.get("/provisioning/{account_id}/oauth-status", dependencies=[Depends(require_agent_token)])
def oauth_status_for_agent(account_id: str) -> dict:
    """OAuth connection status for the inline agent connect flow (no token material)."""
    status = oauth_svc.connection_status(account_id)
    return {
        "account_id": account_id,
        "connected": status.connected,
        "x_user_id": status.x_user_id,
        "x_username": status.x_username,
        "unverified": status.unverified,
    }


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
    # Single non-blocking snapshot — the modal polls on its own interval, so this
    # route must return immediately instead of long-polling Mailgun for ~180s
    # (which would block the modal's email-then-sms code check from ever reaching
    # the SMS code).
    code = get_disposable_email_client().fetch_code(address, timeout_s=0)
    return {"code": code}


@agent_router.get("/provisioning/{account_id}/phone", dependencies=[Depends(require_agent_token)])
def get_phone(account_id: str) -> dict:
    """Return the persistent rental number assigned to this account, if any."""
    sec = secrets_svc.get(account_id)
    return {"phone": (sec.disposable_phone if sec else None)}


@agent_router.post("/provisioning/{account_id}/phone", dependencies=[Depends(require_agent_token)])
def assign_phone(account_id: str, body: PhoneAssignBody) -> dict:
    """Assign + persist the rental number the operator entered for this account.

    No new number is acquired — each account keeps ONE consistent rental number in
    RavenDB, so the number (and password) persist across re-auth / restarts.
    """
    num = (body.phone or "").strip()
    if not num:
        raise HTTPException(status_code=400, detail="phone is required")
    secrets_svc.upsert(account_id, disposable_phone=num)
    return {"phone": num}


@agent_router.get("/provisioning/{account_id}/phone-code", dependencies=[Depends(require_agent_token)])
def phone_code(account_id: str) -> dict:
    """Listen for the latest SMS code on this account's assigned (rental) number."""
    sec = secrets_svc.get(account_id)
    num = (sec.disposable_phone if sec else None)
    if not num:
        raise HTTPException(status_code=409, detail="no phone assigned for account")
    code = get_disposable_phone_client().fetch_code_by_number(num)
    return {"code": code}

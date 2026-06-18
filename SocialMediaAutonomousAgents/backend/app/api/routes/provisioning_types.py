"""Wire types + SSE helpers for the provisioning routes.

Two trust domains share these models: the dashboard (frontend) sets control and
reads status; the local agent fetches a job, pushes status, and posts a result.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.models.account import AccountProvisioning


class ProvisioningJob(BaseModel):
    """Spec + disposable creds the agent needs to drive signup."""
    account_id: str
    handle: str
    display_name: str
    bio: str
    avatar_asset_id: str | None
    header_asset_id: str | None
    email: str
    card: dict | None = None  # {number, exp, cvv, name} from .env, only if configured


class ProvisioningResult(BaseModel):
    """Outcome the agent posts back; secrets land encrypted in AccountSecrets."""
    x_user_id: str = ""
    dev_app_id: str = ""
    password: str | None = None
    session_cookies: str | None = None
    dev_api_key: str | None = None
    dev_api_secret: str | None = None
    dev_bearer_token: str | None = None


class StatusUpdate(BaseModel):
    status: str
    current_page: str = ""
    note: str | None = None
    x_user_id: str = ""
    dev_app_id: str = ""


class ControlBody(BaseModel):
    action: Literal["continue", "cancel"]


# ── SSE emit helpers for the frontend status stream ──

def emit_status(p: AccountProvisioning) -> dict:
    return {
        "type": "status",
        "status": p.status,
        "current_page": p.current_page,
        "step_log": list(p.step_log),
        "error_message": p.error_message,
        "attempt_count": p.attempt_count,
        "x_user_id": p.x_user_id,
        "dev_app_id": p.dev_app_id,
    }


def emit_done() -> dict:
    return {"type": "done"}


def emit_error(msg: str) -> dict:
    return {"type": "error", "message": msg}

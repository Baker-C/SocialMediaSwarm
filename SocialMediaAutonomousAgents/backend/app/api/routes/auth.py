"""Dashboard login gate.

Stateless: no server-side session store. On a correct password we mint a signed
token `"{exp}.{hmac_sha256(secret, exp)}"` that the frontend keeps in localStorage
and sends as `Authorization: Bearer <token>`. The same secret verifies it later, so
nothing about the session is persisted on the backend.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


def _session_secret() -> str:
    return settings.dashboard_session_secret or settings.encryption_key


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sign(exp: int) -> str:
    mac = hmac.new(_session_secret().encode("utf-8"), str(exp).encode("utf-8"), hashlib.sha256)
    return f"{exp}.{mac.hexdigest()}"


def _verify(token: str) -> bool:
    try:
        exp_str, _ = token.split(".", 1)
        exp = int(exp_str)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(token, _sign(exp)):
        return False
    return exp > int(time.time())


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: int


def require_auth(authorization: str = Header(default="")) -> None:
    """Dependency: reject requests without a valid bearer token.

    Auth is a no-op when DASHBOARD_PASSWORD is unset (local dev / not yet exposed)."""
    if not settings.dashboard_password:
        return
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not _verify(token.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not settings.dashboard_password:
        raise HTTPException(status_code=400, detail="Login is not configured")
    if not hmac.compare_digest(_hash(body.password), _hash(settings.dashboard_password)):
        raise HTTPException(status_code=401, detail="Incorrect password")
    exp = int(time.time()) + settings.dashboard_session_days * 86_400
    return LoginResponse(token=_sign(exp), expires_at=exp)

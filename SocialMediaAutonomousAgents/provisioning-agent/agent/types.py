"""Lightweight, SELF-CONTAINED local types for the agent.

These mirror the backend's provisioning types (05 §2) by shape, but the agent never
imports the backend — it is a standalone package. Wire-level (de)serialization happens
in :mod:`agent.backend_client`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProvisioningJob:
    """Spec + disposable creds the agent needs (mirror of backend ProvisioningJob)."""

    account_id: str
    handle: str
    display_name: str
    bio: str
    email: str
    avatar_asset_id: Optional[str] = None
    header_asset_id: Optional[str] = None
    card: Optional[dict] = None  # {number, exp, cvv, name} or None for the free-tier path

    @classmethod
    def from_dict(cls, d: dict) -> "ProvisioningJob":
        return cls(
            account_id=d["account_id"],
            handle=d.get("handle", ""),
            display_name=d.get("display_name", ""),
            bio=d.get("bio", ""),
            email=d["email"],
            avatar_asset_id=d.get("avatar_asset_id"),
            header_asset_id=d.get("header_asset_id"),
            card=d.get("card"),
        )


@dataclass
class ProvisioningResult:
    """Outcome posted back to the backend (mirror of backend ProvisioningResult)."""

    x_user_id: str = ""
    dev_app_id: str = ""
    password: Optional[str] = None
    session_cookies: Optional[str] = None
    dev_api_key: Optional[str] = None
    dev_api_secret: Optional[str] = None
    dev_bearer_token: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "x_user_id": self.x_user_id,
            "dev_app_id": self.dev_app_id,
            "password": self.password,
            "session_cookies": self.session_cookies,
            "dev_api_key": self.dev_api_key,
            "dev_api_secret": self.dev_api_secret,
            "dev_bearer_token": self.dev_bearer_token,
        }


@dataclass
class HandlerResult:
    advanced: bool = True  # took an action and expects the page to change
    needs_user: bool = False  # pause (CAPTCHA)
    failed: bool = False
    error: Optional[str] = None
    status_note: Optional[str] = None  # pushed to backend step_log


@dataclass
class AgentContext:
    """Carries the backend client, the job, fetched media bytes, and the accumulating result.

    Typed against the BackendClient protocol so tests can inject a FakeBackend.
    """

    backend: "object"  # BackendPort (see backend_client); kept loose to avoid an import cycle
    job: ProvisioningJob
    result: ProvisioningResult = field(default_factory=ProvisioningResult)
    avatar_bytes: Optional[bytes] = None
    header_bytes: Optional[bytes] = None

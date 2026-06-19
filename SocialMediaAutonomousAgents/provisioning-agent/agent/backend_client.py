"""Typed httpx wrapper over the backend agent routes (05 §3).

Presents ``Authorization: Bearer <PROVISIONING_AGENT_TOKEN>``. The agent never holds
provider secrets: disposable email/phone helpers proxy through the backend (07).

httpx is imported at module top because it is a declared, always-available dependency
(unlike playwright). All decision logic in the package is tested against the
:class:`BackendPort` protocol via a fake, so this concrete client needs no test.
"""
from __future__ import annotations

from typing import Optional, Protocol

import httpx

from .types import ProvisioningJob, ProvisioningResult


class BackendPort(Protocol):
    """The slice of backend behavior the agent depends on (so tests can fake it)."""

    def fetch_job(self) -> ProvisioningJob: ...
    def push_status(
        self,
        *,
        status: str,
        current_page: str = "",
        note: Optional[str] = None,
        x_user_id: str = "",
        dev_app_id: str = "",
    ) -> None: ...
    def poll_control(self) -> str: ...  # "" | "continue" | "cancel"
    def post_result(self, result: ProvisioningResult) -> None: ...

    # disposable creds proxied through the backend (07)
    def fetch_email_code(self) -> str: ...
    def create_phone(self) -> str: ...
    def fetch_sms_code(self) -> str: ...

    # media bytes for the avatar/header (fetched once by run.py)
    def fetch_asset(self, asset_id: str) -> bytes: ...


class BackendClient:
    """Concrete :class:`BackendPort` over httpx."""

    def __init__(self, base_url: str, agent_token: str, account_id: str, *, timeout: float = 30.0) -> None:
        self._account_id = account_id
        self._base = f"{base_url.rstrip('/')}/provisioning/{account_id}"
        self._assets_base = f"{base_url.rstrip('/')}/provisioning/{account_id}"
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {agent_token}"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BackendClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- core agent routes (05) ----
    def fetch_job(self) -> ProvisioningJob:
        r = self._client.get(f"{self._base}/job")
        r.raise_for_status()
        return ProvisioningJob.from_dict(r.json())

    def push_status(
        self,
        *,
        status: str,
        current_page: str = "",
        note: Optional[str] = None,
        x_user_id: str = "",
        dev_app_id: str = "",
    ) -> None:
        r = self._client.post(
            f"{self._base}/status",
            json={
                "status": status,
                "current_page": current_page,
                "note": note,
                "x_user_id": x_user_id,
                "dev_app_id": dev_app_id,
            },
        )
        r.raise_for_status()

    def poll_control(self) -> str:
        r = self._client.get(f"{self._base}/control")
        r.raise_for_status()
        return r.json().get("action", "") or ""

    def post_result(self, result: ProvisioningResult) -> None:
        r = self._client.post(f"{self._base}/result", json=result.to_dict())
        r.raise_for_status()

    # ---- disposable-creds proxies (07) ----
    def fetch_email_code(self) -> str:
        r = self._client.get(f"{self._base}/email-code")
        r.raise_for_status()
        return r.json().get("code", "") or ""

    def create_phone(self) -> str:
        r = self._client.post(f"{self._base}/phone")
        r.raise_for_status()
        return r.json().get("phone", "") or ""

    def fetch_sms_code(self) -> str:
        r = self._client.get(f"{self._base}/phone-code")
        r.raise_for_status()
        return r.json().get("code", "") or ""

    # ---- media ----
    def fetch_asset(self, asset_id: str) -> bytes:
        r = self._client.get(f"{self._assets_base}/asset/{asset_id}")
        r.raise_for_status()
        return r.content

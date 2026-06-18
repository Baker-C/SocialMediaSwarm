"""Disposable phone: SIM-based OTP-receive provider (5sim/TextVerified-style).

VoIP/Twilio numbers are rejected by X (2026), so this must front a SIM tier. Numbers
cost per-use, so the agent only acquires one when a phone page actually appears. The
provider is pluggable behind the private `_provider_*` methods.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DisposablePhoneError(RuntimeError):
    """HTTP failure, no number available, or unexpected provider payload."""


@dataclass
class PhoneLease:
    lease_id: str
    phone: str


class DisposablePhoneClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._base_url = (settings.disposable_phone_api_base or "").rstrip("/")
        self._api_key = (settings.disposable_phone_api_key or "").strip()
        self._country = (settings.disposable_phone_country or "").strip()

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _require_base(self) -> None:
        if not self._base_url:
            raise DisposablePhoneError("DISPOSABLE_PHONE_API_BASE is not set")

    def _provider_acquire(self, *, service: str, country: str) -> dict:
        self._require_base()
        url = f"{self._base_url}/acquire"
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                url, headers=self._headers(), params={"service": service, "country": country}
            )
        if resp.status_code >= 400:
            raise DisposablePhoneError(
                f"phone acquire HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if not isinstance(data, dict) or not data.get("id") or not data.get("phone"):
            raise DisposablePhoneError(f"phone acquire missing id/phone: {data!r}")
        return data

    def _provider_messages(self, lease_id: str) -> str:
        self._require_base()
        url = f"{self._base_url}/messages"
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self._headers(), params={"id": lease_id})
        if resp.status_code >= 400:
            raise DisposablePhoneError(
                f"phone messages HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if isinstance(data, dict):
            return str(data.get("sms") or data.get("text") or data.get("code") or "")
        return str(data or "")

    def _provider_release(self, lease_id: str) -> None:
        self._require_base()
        url = f"{self._base_url}/release"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=self._headers(), params={"id": lease_id})
        if resp.status_code >= 400:
            logger.warning(
                "phone release HTTP %s for lease=%s: %s",
                resp.status_code,
                lease_id,
                resp.text[:300],
            )

    def acquire_number(
        self, *, service: str = "twitter", country: str | None = None
    ) -> PhoneLease:
        """Lease a SIM number for X; returns a PhoneLease. Raises if none available."""
        data = self._provider_acquire(service=service, country=(country or self._country))
        return PhoneLease(lease_id=str(data["id"]), phone=str(data["phone"]))

    def fetch_code(
        self, lease_id: str, *, timeout_s: int = 240, pattern: str = r"\b\d{6}\b"
    ) -> str | None:
        """Poll the provider for the SMS to this lease; regex the code, else None."""
        rx = re.compile(pattern)
        deadline = time.monotonic() + max(0, int(timeout_s))
        interval = 5.0
        while True:
            try:
                sms = self._provider_messages(lease_id)
            except DisposablePhoneError as exc:
                logger.warning("disposable_phone fetch_code read failed: %s", exc)
                sms = ""
            m = rx.search(sms)
            if m:
                return m.group(0)
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)

    def release(self, lease_id: str) -> None:
        self._provider_release(lease_id)


_client: DisposablePhoneClient | None = None


def get_disposable_phone_client() -> DisposablePhoneClient:
    global _client
    if _client is None:
        _client = DisposablePhoneClient()
    return _client

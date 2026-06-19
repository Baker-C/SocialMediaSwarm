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
    """Phone OTP client backed by n8n Vonage workflows (Acquire + Fetch SMS)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def acquire_number(
        self, *, service: str = "twitter", country: str | None = None
    ) -> PhoneLease:
        """Lease a SIM number for X via n8n Vonage workflow; returns a PhoneLease."""
        n8n_url = "https://xswarm.app.n8n.cloud/webhook/acquire-phone"
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(n8n_url, json={"service": service, "country": country or "US"})
            resp.raise_for_status()
            data = resp.json()
            return PhoneLease(lease_id=str(data.get("lease_id")), phone=str(data.get("phone")))
        except Exception as exc:
            raise DisposablePhoneError(f"n8n acquire_phone failed: {exc}") from exc

    def fetch_code(
        self, lease_id: str, *, timeout_s: int = 240, pattern: str = r"\b\d{6}\b"
    ) -> str | None:
        """Poll n8n Vonage workflow for the SMS code to this lease; regex the code, else None."""
        rx = re.compile(pattern)
        deadline = time.monotonic() + max(0, int(timeout_s))
        interval = 5.0
        n8n_url = f"https://xswarm.app.n8n.cloud/webhook/fetch-sms/{lease_id}"

        while True:
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(n8n_url)
                resp.raise_for_status()
                data = resp.json()
                code = data.get("code", "")
                if code:
                    m = rx.search(code)
                    if m:
                        return m.group(0)
            except Exception as exc:
                logger.warning("disposable_phone fetch_code n8n request failed: %s", exc)

            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)

    def release(self, lease_id: str) -> None:
        """Release the phone lease (cleanup via n8n workflow)."""
        # n8n workflows handle cleanup; this is a no-op locally
        pass


_client: DisposablePhoneClient | None = None


def get_disposable_phone_client() -> DisposablePhoneClient:
    global _client
    if _client is None:
        _client = DisposablePhoneClient()
    return _client

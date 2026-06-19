"""Disposable email client backed by n8n Mailgun workflows (Create Inbox + Fetch Code)."""

from __future__ import annotations

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)


class DisposableEmailError(RuntimeError):
    """n8n workflow error or mailbox API failure."""


class DisposableEmailClient:
    """Email OTP client backed by n8n Mailgun workflows (Create Inbox + Fetch Code)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def create_inbox(self, account_id: str) -> str:
        """Create a disposable email inbox via n8n workflow."""
        n8n_url = "https://xswarm.app.n8n.cloud/webhook/acquire-email"
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(n8n_url, json={"account_id": account_id})
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("email"))
        except Exception as exc:
            raise DisposableEmailError(f"n8n create_inbox failed: {exc}") from exc

    def fetch_code(
        self, address: str, *, timeout_s: int = 180, pattern: str = r"\b\d{6}\b"
    ) -> str | None:
        """Poll n8n Mailgun workflow for the verification code to `address`; regex it, else None."""
        rx = re.compile(pattern)
        deadline = time.monotonic() + max(0, int(timeout_s))
        interval = 5.0
        n8n_url = f"https://xswarm.app.n8n.cloud/webhook/fetch-email-code/{address}"

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
                logger.warning("disposable_email fetch_code n8n request failed: %s", exc)

            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)


_client: DisposableEmailClient | None = None


def get_disposable_email_client() -> DisposableEmailClient:
    global _client
    if _client is None:
        _client = DisposableEmailClient()
    return _client

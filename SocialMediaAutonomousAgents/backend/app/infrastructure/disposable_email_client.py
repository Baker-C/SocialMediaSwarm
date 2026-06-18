"""Disposable email: mint catch-all addresses on an owned domain and read codes.

Addresses live on `settings.disposable_email_domain` with Cloudflare Email Routing
catch-all forwarding into a mailbox read API (`settings.disposable_email_api_base`).
"Creating" an inbox is just minting an address — no network call (catch-all). The
provider read is abstracted behind `_fetch_messages` so the mailbox backend
(Cloudflare Worker/KV, IMAP bridge, mail.tm) can change without touching callers.
"""

from __future__ import annotations

import logging
import re
import secrets
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DisposableEmailError(RuntimeError):
    """HTTP failure or unexpected mailbox payload."""


def _slug(account_id: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", (account_id or "").lower())
    return s or "acct"


class DisposableEmailClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._base_url = (settings.disposable_email_api_base or "").rstrip("/")
        self._api_key = (settings.disposable_email_api_key or "").strip()
        self._domain = (settings.disposable_email_domain or "").strip()

    def create_inbox(self, account_id: str) -> str:
        """Mint a fresh catch-all address `{slug}-{rand}@{domain}`. No network call."""
        if not self._domain:
            raise DisposableEmailError("DISPOSABLE_EMAIL_DOMAIN is not set")
        rand = secrets.token_hex(4)
        return f"{_slug(account_id)}-{rand}@{self._domain}"

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _fetch_messages(self, address: str) -> list[dict]:
        """Provider read: latest messages for `address`. Pluggable behind this method."""
        if not self._base_url:
            raise DisposableEmailError("DISPOSABLE_EMAIL_API_BASE is not set")
        url = f"{self._base_url}/messages"
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers=self._headers(), params={"address": address})
        if resp.status_code >= 400:
            raise DisposableEmailError(
                f"mailbox read HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("messages") or data.get("items") or []
        return data if isinstance(data, list) else []

    def fetch_code(
        self, address: str, *, timeout_s: int = 180, pattern: str = r"\b\d{6}\b"
    ) -> str | None:
        """Poll the mailbox for `address`; regex the verification code, else None."""
        rx = re.compile(pattern)
        deadline = time.monotonic() + max(0, int(timeout_s))
        interval = 5.0
        while True:
            try:
                messages = self._fetch_messages(address)
            except DisposableEmailError as exc:
                logger.warning("disposable_email fetch_code read failed: %s", exc)
                messages = []
            for msg in messages:
                body = " ".join(
                    str(msg.get(k) or "") for k in ("subject", "text", "body", "html")
                )
                m = rx.search(body)
                if m:
                    return m.group(0)
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)


_client: DisposableEmailClient | None = None


def get_disposable_email_client() -> DisposableEmailClient:
    global _client
    if _client is None:
        _client = DisposableEmailClient()
    return _client

"""Disposable phone: TextVerified SIM-based OTP via the official `textverified` client.

VoIP/Twilio numbers are rejected by X (2026), so this fronts TextVerified's SIM tier.
Numbers cost per-use, so acquisition is made idempotent per account at the route layer
(reuse a saved number instead of paying again). `fetch_code` is a NON-blocking snapshot
(uses sms.list, not the blocking sms.incoming) so the route returns fast and the caller
polls — which is how the live modal display works.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

_SERVICE = "twitter"
_CODE_PATTERN = r"\b\d{4,8}\b"


class DisposablePhoneError(RuntimeError):
    """TextVerified API failure, no number available, or unexpected payload."""


@dataclass
class PhoneLease:
    lease_id: str  # TextVerified verification id
    phone: str


class DisposablePhoneClient:
    """Phone OTP client backed by the TextVerified `textverified` package."""

    def __init__(self) -> None:
        self._client = None
        # Manual-mode overrides keyed by lease_id (operator-provided OTP), kept for the
        # existing /phone-input route; takes precedence over the live API when present.
        self._manual: dict[str, dict] = {}

    def _tv(self):
        if self._client is None:
            from textverified import TextVerified  # lazy import keeps tests light

            key = (settings.textverified_api_key or "").strip()
            user = (settings.textverified_api_username or "").strip()
            if not key or not user:
                raise DisposablePhoneError(
                    "TEXTVERIFIED_API_KEY / TEXTVERIFIED_API_USERNAME not configured"
                )
            self._client = TextVerified(api_key=key, api_username=user)
        return self._client

    def acquire_number(self, *, service: str = _SERVICE, country: str | None = None) -> PhoneLease:
        """Reserve a SIM number for X via TextVerified; returns a PhoneLease."""
        try:
            from textverified import NewVerificationRequest, ReservationCapability

            client = self._tv()
            req = NewVerificationRequest(
                service_name=service or _SERVICE,
                capability=ReservationCapability.SMS,
            )
            v = client.verifications.create(req)
            phone = str(getattr(v, "number", "") or "").strip()
            lease_id = str(getattr(v, "id", "") or "").strip()
            if not phone or not lease_id:
                raise DisposablePhoneError("TextVerified returned no number/id")
            return PhoneLease(lease_id=lease_id, phone=phone)
        except DisposablePhoneError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface a clean error to the route
            raise DisposablePhoneError(f"TextVerified acquire failed: {exc}") from exc

    def fetch_code(self, lease_id: str, *, pattern: str = _CODE_PATTERN) -> str | None:
        """Non-blocking snapshot of the latest SMS code for this verification, else None."""
        man = self._manual.get(lease_id)
        if man and man.get("code"):
            return str(man["code"])
        try:
            client = self._tv()
            verification = client.verifications.details(lease_id)
            for m in client.sms.list(verification):
                # Prefer the full code from the message body — TextVerified's
                # parsed_code drops leading zeros (e.g. "035202" -> "35202").
                text = getattr(m, "sms_content", None) or getattr(m, "content", None) or ""
                hit = re.search(pattern, str(text))
                if hit:
                    return hit.group(0)
                code = getattr(m, "parsed_code", None)
                if code:
                    return str(code)
            return None
        except Exception as exc:  # noqa: BLE001 — caller polls; a miss is not fatal
            logger.warning("textverified fetch_code failed for %s: %s", lease_id, exc)
            return None

    def fetch_code_by_number(self, number: str, *, pattern: str = _CODE_PATTERN) -> str | None:
        """Non-blocking snapshot of the latest SMS code received on a specific NUMBER.

        Used for persistent rental numbers assigned per account: we listen by the
        number (not a one-shot verification id), so the same number keeps working
        across signups and re-auth challenges.
        """
        num = str(number or "").strip()
        if not num:
            return None
        try:
            client = self._tv()
            for m in client.sms.list(to_number=num):
                # Prefer the full code from the body — parsed_code drops leading digits.
                text = getattr(m, "sms_content", None) or getattr(m, "content", None) or ""
                hit = re.search(pattern, str(text))
                if hit:
                    return hit.group(0)
                code = getattr(m, "parsed_code", None)
                if code:
                    return str(code)
            return None
        except Exception as exc:  # noqa: BLE001 — caller polls; a miss is not fatal
            logger.warning("textverified fetch_code_by_number failed for %s: %s", num, exc)
            return None

    def set_manual_phone(self, lease_id: str, phone: str, code: str) -> None:
        """Manual OTP mode: operator supplies the number + code directly."""
        self._manual[lease_id] = {"phone": phone, "code": code}

    def release(self, lease_id: str) -> None:
        # TextVerified verifications expire on their own; nothing to release synchronously.
        return None


_client: DisposablePhoneClient | None = None


def get_disposable_phone_client() -> DisposablePhoneClient:
    global _client
    if _client is None:
        _client = DisposablePhoneClient()
    return _client

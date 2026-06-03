"""OAuth2 token rotation for active X accounts."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.utils.encryption import decrypt_value, encrypt_value, fernet_from_key

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = "https://api.x.com/2/oauth2/token"


@dataclass
class RefreshResult:
    refreshed: int = 0
    skipped_no_refresh: int = 0
    failed: int = 0


class TwitterOAuth2RefreshService:
    def __init__(self, repo: AccountRepository | None = None) -> None:
        self._repo = repo or AccountRepository()

    def _fernet(self):
        key = (settings.encryption_key or "").strip()
        if not key:
            return None
        return fernet_from_key(key)

    def _can_refresh(self, acc: AccountDocument) -> bool:
        return bool((acc.credentials.oauth2_refresh_token_enc or "").strip())

    def _refresh_one(self, acc: AccountDocument) -> bool:
        f = self._fernet()
        if f is None:
            raise ValueError("ENCRYPTION_KEY is missing or empty; cannot rotate OAuth2 tokens")

        refresh_enc = (acc.credentials.oauth2_refresh_token_enc or "").strip()
        if not refresh_enc:
            return False
        refresh_token = decrypt_value(f, refresh_enc).strip()
        if not refresh_token:
            return False

        client_id = (settings.twitter_oauth2_client_id or "").strip()
        client_secret = (settings.twitter_oauth2_client_secret or "").strip()
        if not client_id:
            raise ValueError("TWITTER_OAUTH2_CLIENT_ID is required for OAuth2 token refresh")

        body = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "client_id": client_id,
        }
        auth = (client_id, client_secret) if client_secret else None
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                TOKEN_ENDPOINT,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=auth,
            )
        if resp.status_code >= 400:
            raise ValueError(f"oauth2 refresh failed: HTTP {resp.status_code} {resp.text[:300]}")
        payload = resp.json()
        access = str(payload.get("access_token") or "").strip()
        if not access:
            raise ValueError("oauth2 refresh response missing access_token")
        new_refresh = str(payload.get("refresh_token") or "").strip()

        acc.credentials.oauth2_access_token_enc = encrypt_value(f, access)
        if new_refresh:
            acc.credentials.oauth2_refresh_token_enc = encrypt_value(f, new_refresh)
        self._repo.save(acc)
        return True

    def refresh_active_accounts(self, *, batch_size: int) -> RefreshResult:
        res = RefreshResult()
        for idx, acc in enumerate(self._repo.list_active()):
            if idx >= max(1, int(batch_size)):
                break
            if not self._can_refresh(acc):
                res.skipped_no_refresh += 1
                continue
            try:
                changed = self._refresh_one(acc)
                if changed:
                    res.refreshed += 1
                else:
                    res.skipped_no_refresh += 1
            except Exception as exc:
                res.failed += 1
                logger.warning("oauth2_refresh: account_id=%s failed: %s", acc.account_id, exc)
        return res


"""X OAuth 2.0 authorization code flow, token storage, and auto-refresh."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.models.oauth_token import OAuthSessionDocument, OAuthTokenDocument
from app.services.account_repository import AccountRepository
from app.services.oauth_pkce import generate_code_challenge, generate_code_verifier, generate_state
from app.services.oauth_exceptions import ReauthRequired, XOAuthError
from app.services.oauth_token_repository import OAuthTokenRepository
from app.social.credentials import XOAuth2UserCredentials
from app.utils.encryption import decrypt_value, encrypt_value, fernet_from_key

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_ENDPOINT = "https://api.x.com/2/oauth2/token"
REFRESH_BUFFER_SECONDS = 300


@dataclass
class RefreshResult:
    refreshed: int = 0
    skipped_no_refresh: int = 0
    failed: int = 0


@dataclass
class OAuthConnectionStatus:
    connected: bool
    expires_at: str | None = None
    scopes: str | None = None
    x_user_id: str | None = None
    updated_at: str | None = None


class TwitterOAuth2Service:
    def __init__(
        self,
        token_repo: OAuthTokenRepository | None = None,
        account_repo: AccountRepository | None = None,
    ) -> None:
        self._tokens = token_repo or OAuthTokenRepository()
        self._accounts = account_repo or AccountRepository()

    def _fernet(self):
        key = (settings.encryption_key or "").strip()
        if not key:
            return None
        return fernet_from_key(key)

    def _client_credentials(self) -> tuple[str, str]:
        client_id = (settings.twitter_oauth2_client_id or "").strip()
        client_secret = (settings.twitter_oauth2_client_secret or "").strip()
        if not client_id:
            raise ValueError("TWITTER_OAUTH2_CLIENT_ID is required")
        return client_id, client_secret

    def _redirect_uri(self) -> str:
        uri = (settings.twitter_oauth2_redirect_uri or "").strip()
        if not uri:
            raise ValueError("TWITTER_OAUTH2_REDIRECT_URI is required")
        return uri

    def _scopes(self) -> str:
        return (settings.twitter_oauth2_scopes or "").strip() or (
            "tweet.read tweet.write users.read follows.read offline.access"
        )

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _expires_at(self, expires_in: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(expires_in)))).isoformat()

    def _parse_expires(self, expires_at: str) -> datetime:
        return datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

    def _encrypt(self, value: str) -> str:
        f = self._fernet()
        if f is None:
            raise ValueError("ENCRYPTION_KEY is missing or empty; cannot store OAuth2 tokens")
        return encrypt_value(f, value.strip())

    def _decrypt(self, enc: str) -> str:
        f = self._fernet()
        if f is None:
            raise ValueError("ENCRYPTION_KEY is missing or empty; cannot decrypt OAuth2 tokens")
        return decrypt_value(f, enc).strip()

    def connection_status(self, account_id: str) -> OAuthConnectionStatus:
        token = self._tokens.load_token(account_id)
        if token is None:
            return OAuthConnectionStatus(connected=False)
        connected = self.is_connected(account_id)
        return OAuthConnectionStatus(
            connected=connected,
            expires_at=token.expires_at,
            scopes=token.scopes or None,
            x_user_id=token.x_user_id,
            updated_at=token.updated_at,
        )

    def is_connected(self, account_id: str) -> bool:
        token = self._tokens.load_token(account_id)
        if token is None or not (token.access_token_enc or "").strip():
            return False
        if (token.refresh_token_enc or "").strip():
            return True
        try:
            return self._parse_expires(token.expires_at) > datetime.now(timezone.utc)
        except Exception:
            return True

    def build_authorization_url(self, account_id: str) -> dict[str, str]:
        aid = (account_id or "").strip()
        if not aid:
            raise ValueError("account_id is required")
        if self._accounts.load(aid) is None:
            raise LookupError(f"Account not found: {aid}")

        client_id, _ = self._client_credentials()
        redirect_uri = self._redirect_uri()
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)
        state = generate_state()
        session_ttl = max(60, int(settings.oauth2_session_ttl_seconds))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=session_ttl)).isoformat()

        self._tokens.save_session(
            OAuthSessionDocument(
                state=state,
                account_id=aid,
                code_verifier=verifier,
                expires_at=expires_at,
            )
        )

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": self._scopes(),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",
        }
        return {
            "account_id": aid,
            "authorization_url": f"{AUTHORIZE_URL}?{urlencode(params)}",
            "state": state,
        }

    @staticmethod
    def _parse_token_error_response(resp: httpx.Response) -> tuple[str, str | None]:
        try:
            payload = resp.json()
        except Exception:
            return "unknown_error", (resp.text or "")[:500] or None
        if not isinstance(payload, dict):
            return "unknown_error", (resp.text or "")[:500] or None
        error = str(payload.get("error") or "unknown_error").strip()
        desc = payload.get("error_description")
        error_description = str(desc).strip() if desc is not None else None
        return error, error_description or None

    def _post_token(self, body: dict[str, str]) -> dict:
        client_id, client_secret = self._client_credentials()
        auth = (client_id, client_secret) if client_secret else None
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                TOKEN_ENDPOINT,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=auth,
            )
        if resp.status_code >= 400:
            error, error_description = self._parse_token_error_response(resp)
            logger.error(
                "oauth2 token request failed: error=%s error_description=%s http=%s",
                error,
                error_description,
                resp.status_code,
            )
            raise XOAuthError(error, error_description, http_status=resp.status_code)
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("oauth2 token response was not a JSON object")
        return payload

    def _handle_exchange_oauth_error(self, exc: XOAuthError, *, state: str) -> None:
        if exc.error == "invalid_grant":
            self._tokens.delete_session(state)
            raise ValueError(
                "Authorization code expired or already used. "
                "Please restart X connection from GET /api/oauth/x/authorize."
            ) from exc
        if exc.error == "invalid_client":
            logger.critical(
                "oauth2 exchange invalid_client: error_description=%s",
                exc.error_description,
            )
            raise ValueError(
                "X OAuth client configuration error (invalid_client). "
                "Verify TWITTER_OAUTH2_CLIENT_ID and TWITTER_OAUTH2_CLIENT_SECRET."
            ) from exc
        if exc.error == "access_denied":
            self._tokens.delete_session(state)
            raise ValueError(
                "X authorization was denied. Please try connecting again."
            ) from exc
        if exc.error == "invalid_request":
            self._tokens.delete_session(state)
            detail = exc.error_description or "Invalid OAuth request."
            raise ValueError(f"OAuth request failed: {detail}") from exc
        detail = exc.error_description or str(exc)
        raise ValueError(f"OAuth token exchange failed: {detail}") from exc

    def _handle_refresh_oauth_error(self, exc: XOAuthError, *, account_id: str) -> None:
        if exc.error == "invalid_grant":
            self._tokens.delete_token(account_id)
            logger.warning(
                "oauth2 refresh invalid_grant account_id=%s error_description=%s; tokens cleared",
                account_id,
                exc.error_description,
            )
            raise ReauthRequired(
                account_id,
                "X refresh token is no longer valid. Re-authorize via GET /api/oauth/x/authorize.",
            ) from exc
        if exc.error == "invalid_client":
            logger.critical(
                "oauth2 refresh invalid_client account_id=%s error_description=%s",
                account_id,
                exc.error_description,
            )
            raise XOAuthError(
                exc.error,
                "X OAuth client secret is invalid or missing (invalid_client).",
                http_status=exc.http_status,
            ) from exc
        raise exc

    def _store_token_response(self, account_id: str, payload: dict, *, x_user_id: str | None = None) -> OAuthTokenDocument:
        access = str(payload.get("access_token") or "").strip()
        if not access:
            raise ValueError("oauth2 token response missing access_token")
        refresh = str(payload.get("refresh_token") or "").strip() or None
        expires_in = int(payload.get("expires_in") or 7200)
        scopes = str(payload.get("scope") or self._scopes()).strip()
        token = OAuthTokenDocument(
            account_id=account_id,
            x_user_id=x_user_id,
            access_token_enc=self._encrypt(access),
            refresh_token_enc=self._encrypt(refresh) if refresh else None,
            expires_at=self._expires_at(expires_in),
            scopes=scopes,
            updated_at=self._now_iso(),
        )
        self._tokens.save_token(token)
        logger.info("oauth2: stored tokens for account_id=%s expires_at=%s", account_id, token.expires_at)
        return token

    def exchange_authorization_code(self, *, code: str, state: str) -> OAuthTokenDocument:
        code = (code or "").strip()
        state = (state or "").strip()
        if not code or not state:
            raise ValueError("code and state are required")

        session = self._tokens.load_session(state)
        if session is None:
            raise ValueError("invalid or expired OAuth state")
        try:
            if self._parse_expires(session.expires_at) <= datetime.now(timezone.utc):
                self._tokens.delete_session(state)
                raise ValueError("OAuth session expired; restart authorization")
        except ValueError:
            raise
        except Exception:
            pass

        client_id, _ = self._client_credentials()
        body = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": self._redirect_uri(),
            "code_verifier": session.code_verifier,
        }
        try:
            payload = self._post_token(body)
        except XOAuthError as exc:
            self._handle_exchange_oauth_error(exc, state=state)
        token = self._store_token_response(session.account_id, payload)
        self._tokens.delete_session(state)
        return token

    def refresh_account_tokens(self, account_id: str) -> bool:
        token = self._tokens.load_token(account_id)
        if token is None:
            return False
        refresh_enc = (token.refresh_token_enc or "").strip()
        if not refresh_enc:
            return False

        refresh_token = self._decrypt(refresh_enc)
        if not refresh_token:
            return False

        client_id, _ = self._client_credentials()
        body = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "client_id": client_id,
        }
        try:
            payload = self._post_token(body)
        except XOAuthError as exc:
            self._handle_refresh_oauth_error(exc, account_id=account_id)
        self._store_token_response(account_id, payload, x_user_id=token.x_user_id)
        return True

    def _needs_refresh(self, token: OAuthTokenDocument) -> bool:
        refresh_enc = (token.refresh_token_enc or "").strip()
        if not refresh_enc:
            return False
        try:
            exp = self._parse_expires(token.expires_at)
        except Exception:
            return True
        return exp <= datetime.now(timezone.utc) + timedelta(seconds=REFRESH_BUFFER_SECONDS)

    def get_credentials(self, account_id: str, *, auto_refresh: bool = True) -> XOAuth2UserCredentials | None:
        token = self._tokens.load_token(account_id)
        if token is None:
            return None

        if auto_refresh and self._needs_refresh(token):
            try:
                if self.refresh_account_tokens(account_id):
                    token = self._tokens.load_token(account_id)
            except ReauthRequired:
                raise
            except XOAuthError as exc:
                logger.warning(
                    "oauth2: on-demand refresh failed account_id=%s error=%s: %s",
                    account_id,
                    exc.error,
                    exc,
                )
            except Exception as exc:
                logger.warning("oauth2: on-demand refresh failed account_id=%s: %s", account_id, exc)

        if token is None:
            return None

        try:
            access = self._decrypt(token.access_token_enc)
        except ValueError as exc:
            logger.warning("oauth2: decrypt failed account_id=%s: %s", account_id, exc)
            return None
        if not access:
            return None

        refresh: str | None = None
        if token.refresh_token_enc:
            try:
                refresh = self._decrypt(token.refresh_token_enc) or None
            except ValueError:
                refresh = None

        return XOAuth2UserCredentials(access_token=access, refresh_token=refresh)

    def credentials_unavailable_reason(self, account_id: str) -> str:
        if not settings.encryption_key or not settings.encryption_key.strip():
            return "ENCRYPTION_KEY is missing or empty; cannot decrypt OAuth2 tokens"
        token = self._tokens.load_token(account_id)
        if token is None:
            return (
                f"No OAuth2 tokens for account_id={account_id}; "
                "connect via GET /api/oauth/x/authorize?account_id=..."
            )
        if not (token.access_token_enc or "").strip():
            return "OAuth2 token record exists but access token is empty"
        try:
            if self._parse_expires(token.expires_at) <= datetime.now(timezone.utc):
                if token.refresh_token_enc:
                    return "OAuth2 access token expired; refresh pending or failed"
                return "OAuth2 access token expired and no refresh token stored"
        except Exception:
            pass
        return "OAuth2 access token could not be decrypted (wrong ENCRYPTION_KEY or corrupt ciphertext)"

    def disconnect(self, account_id: str) -> None:
        self._tokens.delete_token(account_id)

    def purge_expired_sessions(self) -> int:
        return self._tokens.purge_expired_sessions()

    def refresh_all_tokens(self, *, batch_size: int) -> RefreshResult:
        res = RefreshResult()
        for idx, token in enumerate(self._tokens.list_tokens()):
            if idx >= max(1, int(batch_size)):
                break
            if not (token.refresh_token_enc or "").strip():
                res.skipped_no_refresh += 1
                continue
            if not self._needs_refresh(token):
                res.skipped_no_refresh += 1
                continue
            try:
                if self.refresh_account_tokens(token.account_id):
                    res.refreshed += 1
                else:
                    res.skipped_no_refresh += 1
            except ReauthRequired as exc:
                res.failed += 1
                logger.warning("oauth2_refresh: account_id=%s reauth required: %s", token.account_id, exc)
            except XOAuthError as exc:
                res.failed += 1
                logger.warning(
                    "oauth2_refresh: account_id=%s oauth error=%s: %s",
                    token.account_id,
                    exc.error,
                    exc,
                )
            except Exception as exc:
                res.failed += 1
                logger.warning("oauth2_refresh: account_id=%s failed: %s", token.account_id, exc)
        return res

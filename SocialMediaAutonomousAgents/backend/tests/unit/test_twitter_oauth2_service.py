from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.models.account import AccountDocument
from app.models.oauth_token import OAuthTokenDocument, OAuthSessionDocument
import httpx

from app.services import twitter_oauth2_service as svc_mod
from app.services.oauth_exceptions import ReauthRequired, XOAuthError
from app.services.twitter_oauth2_service import TwitterOAuth2Service


def _token(account_id: str = "aid", *, expires_in_hours: float = 2, key: str | None = None) -> OAuthTokenDocument:
    key = key or Fernet.generate_key().decode()
    from app.utils.encryption import encrypt_value, fernet_from_key

    fernet = fernet_from_key(key)
    exp = (datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).isoformat()
    return OAuthTokenDocument(
        account_id=account_id,
        access_token_enc=encrypt_value(fernet, "access-token"),
        refresh_token_enc=encrypt_value(fernet, "refresh-token"),
        expires_at=exp,
        scopes="tweet.read offline.access",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def test_build_authorization_url_stores_session(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_redirect_uri", "http://localhost/callback")

    accounts = MagicMock()
    accounts.load.return_value = AccountDocument(account_id="aid", niche="n", twitter_handle="", status="active")
    tokens = MagicMock()

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=accounts)
    out = svc.build_authorization_url("aid")
    assert out["account_id"] == "aid"
    assert "authorization_url" in out
    assert "client-id" in out["authorization_url"]
    tokens.save_session.assert_called_once()


def test_get_credentials_auto_refreshes_when_expiring(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_redirect_uri", "http://localhost/callback")

    token = _token(expires_in_hours=-1, key=key)
    tokens = MagicMock()
    tokens.load_token.side_effect = [token, token]

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    with patch.object(svc, "refresh_account_tokens", return_value=True) as refresh:
        creds = svc.get_credentials("aid", auto_refresh=True)
    refresh.assert_called_once_with("aid")
    assert creds is not None
    assert creds.access_token == "access-token"


def test_exchange_authorization_code(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_redirect_uri", "http://localhost/callback")

    session = OAuthSessionDocument(
        state="state-1",
        account_id="aid",
        code_verifier="verifier",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    tokens = MagicMock()
    tokens.load_session.return_value = session

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    with patch.object(
        svc,
        "_post_token",
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 7200,
            "scope": "tweet.read offline.access",
        },
    ):
        out = svc.exchange_authorization_code(code="code-1", state="state-1")
    assert out.account_id == "aid"
    tokens.save_token.assert_called_once()
    tokens.delete_session.assert_called_once_with("state-1")


def test_parse_token_error_response_json() -> None:
    resp = httpx.Response(
        400,
        json={"error": "invalid_grant", "error_description": "code expired"},
    )
    error, desc = TwitterOAuth2Service._parse_token_error_response(resp)
    assert error == "invalid_grant"
    assert desc == "code expired"


def test_post_token_raises_x_oauth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")

    mock_resp = httpx.Response(
        400,
        json={"error": "invalid_client", "error_description": "bad secret"},
    )
    svc = TwitterOAuth2Service(token_repo=MagicMock(), account_repo=MagicMock())
    with patch("app.services.twitter_oauth2_service.httpx.Client") as ClientCls:
        ClientCls.return_value.__enter__.return_value.post.return_value = mock_resp
        with pytest.raises(XOAuthError) as exc_info:
            svc._post_token({"grant_type": "refresh_token"})
    assert exc_info.value.error == "invalid_client"
    assert exc_info.value.error_description == "bad secret"
    assert exc_info.value.http_status == 400


def test_exchange_invalid_grant_clears_session(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_redirect_uri", "http://localhost/callback")

    session = OAuthSessionDocument(
        state="state-1",
        account_id="aid",
        code_verifier="verifier",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    tokens = MagicMock()
    tokens.load_session.return_value = session
    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())

    err = XOAuthError("invalid_grant", "expired code", http_status=400)
    with patch.object(svc, "_post_token", side_effect=err):
        with pytest.raises(ValueError, match="restart X connection"):
            svc.exchange_authorization_code(code="code-1", state="state-1")
    tokens.delete_session.assert_called_once_with("state-1")
    tokens.save_token.assert_not_called()


def test_refresh_invalid_grant_deletes_token_and_raises_reauth(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")

    token = _token(key=key)
    tokens = MagicMock()
    tokens.load_token.return_value = token
    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())

    err = XOAuthError("invalid_grant", "refresh revoked", http_status=400)
    with patch.object(svc, "_post_token", side_effect=err):
        with pytest.raises(ReauthRequired, match="Re-authorize"):
            svc.refresh_account_tokens("aid")
    tokens.delete_token.assert_called_once_with("aid")


def test_refresh_invalid_client_raises_x_oauth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "wrong")

    token = _token(key=key)
    tokens = MagicMock()
    tokens.load_token.return_value = token
    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())

    err = XOAuthError("invalid_client", "bad credentials", http_status=401)
    with patch.object(svc, "_post_token", side_effect=err):
        with pytest.raises(XOAuthError) as exc_info:
            svc.refresh_account_tokens("aid")
    assert exc_info.value.error == "invalid_client"
    assert "client secret" in (exc_info.value.error_description or "").lower()

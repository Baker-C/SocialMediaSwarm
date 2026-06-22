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
    tokens.find_account_by_x_user_id.return_value = None
    tokens.claim_binding.return_value = True

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
    ), patch.object(svc, "_resolve_identity", return_value=("uid-1", "alice")):
        out = svc.exchange_authorization_code(code="code-1", state="state-1")
    assert out.account_id == "aid"
    assert out.x_user_id == "uid-1"
    assert out.x_username == "alice"
    tokens.save_token.assert_called_once()
    tokens.claim_binding.assert_called_once_with("uid-1", "aid")
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


# ── _resolve_identity ──────────────────────────────────────────────────────────

def _identity_svc() -> TwitterOAuth2Service:
    return TwitterOAuth2Service(token_repo=MagicMock(), account_repo=MagicMock())


def test_resolve_identity_returns_id_and_username() -> None:
    svc = _identity_svc()
    resp = httpx.Response(200, json={"data": {"id": "777", "username": "neo"}})
    with patch("app.services.twitter_oauth2_service.httpx.Client") as ClientCls:
        instance = ClientCls.return_value.__enter__.return_value
        instance.get.return_value = resp
        uid, username = svc._resolve_identity("access-token")
    assert uid == "777"
    assert username == "neo"
    # The request must ask for the username field.
    _, kwargs = instance.get.call_args
    assert kwargs["params"] == {"user.fields": "username"}


def test_resolve_identity_retries_then_returns_null() -> None:
    svc = _identity_svc()
    resp = httpx.Response(429, json={"error": "rate limit"})
    with patch("app.services.twitter_oauth2_service.httpx.Client") as ClientCls:
        instance = ClientCls.return_value.__enter__.return_value
        instance.get.return_value = resp
        uid, username = svc._resolve_identity("access-token")
    assert uid is None and username is None
    assert instance.get.call_count == svc_mod.IDENTITY_MAX_ATTEMPTS


def test_exchange_rejects_duplicate_x_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_redirect_uri", "http://localhost/callback")

    session = OAuthSessionDocument(
        state="state-1",
        account_id="aid-new",
        code_verifier="verifier",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    tokens = MagicMock()
    tokens.load_session.return_value = session
    tokens.find_account_by_x_user_id.return_value = "aid-existing"

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    with patch.object(svc, "_post_token", return_value={"access_token": "a", "expires_in": 7200}), patch.object(
        svc, "_resolve_identity", return_value=("dup-uid", "bob")
    ):
        with pytest.raises(ValueError, match="aid-existing"):
            svc.exchange_authorization_code(code="c", state="state-1")
    tokens.save_token.assert_not_called()
    tokens.delete_session.assert_called_once_with("state-1")


def test_exchange_allows_same_account_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
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
    tokens.find_account_by_x_user_id.return_value = "aid"  # same account already bound
    tokens.claim_binding.return_value = True

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    with patch.object(svc, "_post_token", return_value={"access_token": "a", "expires_in": 7200}), patch.object(
        svc, "_resolve_identity", return_value=("uid", "alice")
    ):
        out = svc.exchange_authorization_code(code="c", state="state-1")
    assert out.account_id == "aid"
    tokens.save_token.assert_called_once()


def test_exchange_null_id_not_treated_as_unique(monkeypatch: pytest.MonkeyPatch) -> None:
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
    with patch.object(svc, "_post_token", return_value={"access_token": "a", "expires_in": 7200}), patch.object(
        svc, "_resolve_identity", return_value=(None, None)
    ):
        out = svc.exchange_authorization_code(code="c", state="state-1")
    assert out.x_user_id is None
    # Null identity must never claim/look-up a unique binding.
    tokens.find_account_by_x_user_id.assert_not_called()
    tokens.claim_binding.assert_not_called()
    tokens.save_token.assert_called_once()


def test_refresh_preserves_username(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")

    token = _token(key=key)
    token.x_user_id = "uid-1"
    token.x_username = "alice"
    tokens = MagicMock()
    tokens.load_token.return_value = token

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    captured: dict = {}

    def _capture(account_id, payload, *, x_user_id=None, x_username=None):
        captured["x_user_id"] = x_user_id
        captured["x_username"] = x_username
        return token

    with patch.object(svc, "_post_token", return_value={"access_token": "a", "expires_in": 7200}), patch.object(
        svc, "_store_token_response", side_effect=_capture
    ), patch.object(svc, "_resolve_identity") as resolve:
        assert svc.refresh_account_tokens("aid") is True
    resolve.assert_not_called()
    assert captured == {"x_user_id": "uid-1", "x_username": "alice"}


def test_refresh_self_heals_null_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_id", "client-id")
    monkeypatch.setattr(svc_mod.settings, "twitter_oauth2_client_secret", "secret")

    token = _token(key=key)  # x_user_id/x_username default to None
    tokens = MagicMock()
    tokens.load_token.return_value = token

    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    captured: dict = {}

    def _capture(account_id, payload, *, x_user_id=None, x_username=None):
        captured["x_user_id"] = x_user_id
        captured["x_username"] = x_username
        return token

    with patch.object(svc, "_post_token", return_value={"access_token": "a", "expires_in": 7200}), patch.object(
        svc, "_store_token_response", side_effect=_capture
    ), patch.object(svc, "_resolve_identity", return_value=("healed-uid", "healed")):
        assert svc.refresh_account_tokens("aid") is True
    assert captured == {"x_user_id": "healed-uid", "x_username": "healed"}
    tokens.claim_binding.assert_called_once_with("healed-uid", "aid")


def test_connection_status_exposes_username_and_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(svc_mod.settings, "encryption_key", key)

    # Connected + verified.
    token = _token(key=key)
    token.x_user_id = "uid-1"
    token.x_username = "alice"
    tokens = MagicMock()
    tokens.load_token.return_value = token
    svc = TwitterOAuth2Service(token_repo=tokens, account_repo=MagicMock())
    st = svc.connection_status("aid")
    assert st.connected is True
    assert st.x_username == "alice"
    assert st.unverified is False

    # Connected but identity unresolved → unverified.
    token2 = _token(key=key)
    tokens.load_token.return_value = token2
    st2 = svc.connection_status("aid")
    assert st2.connected is True
    assert st2.unverified is True

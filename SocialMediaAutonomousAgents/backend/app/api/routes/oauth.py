"""X OAuth 2.0 authorization and token management routes."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.infrastructure.ravendb_http import RavenDBHttpError
from app.services.oauth_exceptions import XOAuthError
from app.services.twitter_oauth2_service import TwitterOAuth2Service

router = APIRouter()
oauth_service = TwitterOAuth2Service()


def _frontend_redirect(**params: str) -> RedirectResponse | None:
    base = (settings.twitter_oauth2_success_redirect_url or "").strip().rstrip("/")
    if not base:
        return None
    return RedirectResponse(url=f"{base}?{urlencode(params)}", status_code=302)


@router.get("/oauth/x/setup")
def oauth_setup_info():
    """Portal checklist for X OAuth 2.0 user authentication."""
    redirect_uri = (settings.twitter_oauth2_redirect_uri or "").strip()
    success_url = (settings.twitter_oauth2_success_redirect_url or "").strip()
    website_url = (settings.twitter_oauth2_website_url or "").strip() or "https://example.com"
    scopes = (settings.twitter_oauth2_scopes or "").strip()
    return {
        "redirect_uri": redirect_uri,
        "success_redirect_url": success_url,
        "website_url": website_url,
        "scopes": scopes,
        "portal_checklist": [
            "Developer Portal → your app → User authentication settings → Edit",
            "Enable OAuth 2.0",
            'Type of App: "Web App, Automated App or Bot" (not Native)',
            "App permissions: Read and write",
            f"Callback URI / Redirect URL (exact): {redirect_uri}",
            f"Website URL (https:// + TLD, no port — e.g. https://example.com): {website_url}",
            "Save settings, then Connect with X from the dashboard",
        ],
    }


@router.get("/oauth/x/authorize")
def oauth_authorize(account_id: str = Query(..., min_length=1)):
    """Start OAuth flow; returns the X authorization URL for the given account."""
    try:
        result = oauth_service.build_authorization_url(account_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    result["redirect_uri"] = (settings.twitter_oauth2_redirect_uri or "").strip()
    return result


@router.get("/oauth/x/callback")
def oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """Handle X redirect after user authorization; exchange code for tokens."""
    if error:
        if error == "access_denied":
            detail = (
                error_description
                or "X authorization was denied. Please try connecting again."
            )
        else:
            detail = error_description or error
        message = f"OAuth authorization failed: {detail}"
        redirect = _frontend_redirect(oauth_error=message)
        if redirect is not None:
            return redirect
        raise HTTPException(status_code=400, detail=message)
    if not code.strip() or not state.strip():
        message = (
            "Missing authorization code or state. Restart connection via "
            "GET /api/oauth/x/authorize."
        )
        redirect = _frontend_redirect(oauth_error=message)
        if redirect is not None:
            return redirect
        raise HTTPException(status_code=400, detail=message)
    try:
        token = oauth_service.exchange_authorization_code(code=code, state=state)
    except ValueError as exc:
        redirect = _frontend_redirect(oauth_error=str(exc))
        if redirect is not None:
            return redirect
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except XOAuthError as exc:
        message = f"OAuth token exchange failed: {exc.error_description or exc.error}"
        redirect = _frontend_redirect(oauth_error=message)
        if redirect is not None:
            return redirect
        raise HTTPException(status_code=400, detail=message) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc

    redirect = _frontend_redirect(account_id=token.account_id, connected="1")
    if redirect is not None:
        return redirect
    return {
        "ok": True,
        "account_id": token.account_id,
        "expires_at": token.expires_at,
        "scopes": token.scopes,
    }


@router.get("/oauth/x/status/{account_id}")
def oauth_status(account_id: str):
    """Return whether runtime OAuth tokens exist and are valid for an account."""
    status = oauth_service.connection_status(account_id)
    return {
        "account_id": account_id,
        "connected": status.connected,
        "expires_at": status.expires_at,
        "scopes": status.scopes,
        "x_user_id": status.x_user_id,
        "updated_at": status.updated_at,
    }


@router.delete("/oauth/x/disconnect/{account_id}")
def oauth_disconnect(account_id: str):
    """Remove stored OAuth tokens for an account."""
    try:
        oauth_service.disconnect(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    return {"ok": True, "account_id": account_id, "connected": False}

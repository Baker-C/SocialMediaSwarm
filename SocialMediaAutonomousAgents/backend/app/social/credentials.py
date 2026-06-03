"""Credential bundles passed into platform clients (per-call or per-client)."""

from pydantic import BaseModel, Field


class XOAuth2UserCredentials(BaseModel):
    """OAuth 2.0 user context for X API v2 (Bearer user access token)."""

    access_token: str = Field(..., min_length=1)
    refresh_token: str | None = None

XCredentials = XOAuth2UserCredentials

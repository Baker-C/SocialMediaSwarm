"""Credential bundles passed into platform clients (per-call or per-client)."""

from typing import Union

from pydantic import BaseModel, Field


class XOAuth1Credentials(BaseModel):
    """OAuth 1.0a user context for X (consumer + user access token pair)."""

    consumer_key: str = Field(..., min_length=1)
    consumer_secret: str = Field(..., min_length=1)
    access_token: str = Field(..., min_length=1)
    access_token_secret: str = Field(..., min_length=1)


class XOAuth2UserCredentials(BaseModel):
    """OAuth 2.0 user context for X API v2 (Bearer user access token)."""

    access_token: str = Field(..., min_length=1)
    refresh_token: str | None = None


XCredentials = Union[XOAuth1Credentials, XOAuth2UserCredentials]

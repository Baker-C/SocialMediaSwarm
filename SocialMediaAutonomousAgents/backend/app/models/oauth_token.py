"""Runtime OAuth 2.0 tokens stored separately from account profile documents."""

from pydantic import BaseModel, Field


class OAuthTokenDocument(BaseModel):
    """Per-account X OAuth2 tokens in RavenDB collection ``OAuthTokens``."""

    account_id: str
    x_user_id: str | None = None
    access_token_enc: str
    refresh_token_enc: str | None = None
    expires_at: str
    scopes: str = ""
    updated_at: str

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"oauth-tokens/{account_id}"


class OAuthSessionDocument(BaseModel):
    """Short-lived PKCE session for the authorization code flow."""

    state: str
    account_id: str
    code_verifier: str
    expires_at: str

    @staticmethod
    def document_id(state: str) -> str:
        return f"oauth-sessions/{state}"

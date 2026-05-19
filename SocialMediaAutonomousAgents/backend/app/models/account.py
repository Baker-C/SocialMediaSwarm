"""Account document shape stored in RavenDB (collection Accounts)."""

from pydantic import BaseModel, Field


def default_system_prompt(niche: str) -> str:
    return (
        f"Generate a post about {niche}. "
        "Open with a shocked, opinionated hook (conversational, not newsy) and keep it as one long, "
        "almost run-on sentence with commas—not a chain of short separate sentences. "
        "Post length: 150-280 characters."
    )


class AccountDocument(BaseModel):
    """Full account row in RavenDB. Document id: accounts/{account_id}."""

    account_id: str
    niche: str
    twitter_handle: str = ""
    status: str = "active"
    followers: int = 0
    posts_total: int = 0
    system_prompt: str = Field(default="")
    twitter_api_key_enc: str | None = None
    twitter_api_secret_enc: str | None = None
    twitter_access_token_enc: str | None = None
    twitter_access_token_secret_enc: str | None = None
    # X OAuth 2.0 user context (Bearer user access token; optional refresh for token rotation)
    twitter_oauth2_access_token_enc: str | None = None
    twitter_oauth2_refresh_token_enc: str | None = None
    # Buffer GraphQL (https://developers.buffer.com/guides/data-model.html)
    buffer_organization_id: str | None = None
    buffer_channel_id: str | None = None
    last_post_slot: str | None = None
    # Provenance / dashboard (optional for legacy documents)
    registered_at: str | None = None
    followers_when_registered: int | None = None
    last_post_id: str | None = None
    last_post_text: str | None = None
    last_post_at: str | None = None
    last_post_views: int | None = None

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"accounts/{account_id}"

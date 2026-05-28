"""Account document shape stored in RavenDB (collection Accounts)."""

from pydantic import BaseModel, Field


def default_negative_semantics() -> list[str]:
    """Phrases, structures, and stylistic tells to avoid in composed posts."""
    return [
        "\"It's not that, it's this\" / \"It's not X, it's Y\" false-dichotomy reframes",
        "Similar contrast gimmicks: \"The real story isn't … it's …\", \"This isn't about X, it's about Y\"",
        "Em dash (—) punctuation; use commas or periods instead",
        "\"Same X, same Y — two different things\" / \"same this, same that\" parallel contrast formulas",
        "Obviously AI stock phrases: \"Let's be clear\", \"Here's the thing\", \"Make no mistake\", \"At the end of the day\", \"In today's world\"",
        "Stiff, press-release, or essay voice — write like a person talking, not a bot",
        "AP-style perfect grammar and Title Case on every name — use loose, live X caps instead",
        "Rhetorical question chains or faux-Socratic setup (\"The question isn't … it's …\")",
        "Numbered lesson lists, thread voice, or \"Lesson:\" / \"Thread:\" openers",
    ]


def format_negative_semantics_for_prompt(items: list[str] | None) -> str:
    """Bullet block for compose prompts."""
    cleaned = [s.strip() for s in (items or []) if s and s.strip()]
    if not cleaned:
        cleaned = default_negative_semantics()
    return "\n".join(f"- {line}" for line in cleaned)


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
    # Voice profile for opinion section and tone (personality page / account character)
    personality: str = Field(default="")
    # Banned semantics/phrases/structures for compose (see format_negative_semantics_for_prompt)
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)
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

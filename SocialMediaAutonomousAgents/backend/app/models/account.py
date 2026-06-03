"""Account document shape stored in RavenDB (collection Accounts)."""

from pydantic import AliasChoices, BaseModel, Field, model_validator


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


class AccountProfile(BaseModel):
    niche: str
    twitter_handle: str = ""
    status: str = "active"
    followers: int = 0
    posts_total: int = 0
    # Provenance / dashboard (optional for legacy documents)
    registered_at: str | None = None
    followers_when_registered: int | None = None


class AccountVoice(BaseModel):
    system_prompt: str = Field(default="")
    # Voice profile for opinion section and tone (personality page / account character)
    personality: str = Field(default="")
    # Banned semantics/phrases/structures for compose (see format_negative_semantics_for_prompt)
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)


class AccountCredentials(BaseModel):
    # X OAuth 2.0 user context (Bearer user access token; optional refresh for token rotation)
    oauth2_access_token_enc: str | None = None
    oauth2_refresh_token_enc: str | None = None


class AccountPostingState(BaseModel):
    last_interval_slot: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_interval_slot", "last_post_slot"),
    )
    last_post_id: str | None = None
    last_post_text: str | None = None
    last_post_at: str | None = None
    last_post_views: int | None = None
    # Source tweet ids this account has already reposted (timeline references, not own post ids)
    copied_reference_tweet_ids: list[str] = Field(default_factory=list)


class AccountDocument(BaseModel):
    """Full account row in RavenDB. Document id: accounts/{account_id}."""

    account_id: str
    profile: AccountProfile
    voice: AccountVoice = Field(default_factory=AccountVoice)
    credentials: AccountCredentials = Field(default_factory=AccountCredentials)
    posting: AccountPostingState = Field(default_factory=AccountPostingState)

    @model_validator(mode="before")
    @classmethod
    def _lift_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if "profile" in value:
            return value

        return {
            "account_id": value.get("account_id"),
            "profile": {
                "niche": value.get("niche") or value.get("account_id") or "",
                "twitter_handle": value.get("twitter_handle") or "",
                "status": value.get("status") or "active",
                "followers": value.get("followers") or 0,
                "posts_total": value.get("posts_total") or 0,
                "registered_at": value.get("registered_at"),
                "followers_when_registered": value.get("followers_when_registered"),
            },
            "voice": {
                "system_prompt": value.get("system_prompt") or "",
                "personality": value.get("personality") or "",
                "negative_semantics": value.get("negative_semantics") or default_negative_semantics(),
            },
            "credentials": {
                "oauth2_access_token_enc": value.get("twitter_oauth2_access_token_enc"),
                "oauth2_refresh_token_enc": value.get("twitter_oauth2_refresh_token_enc"),
            },
            "posting": {
                "last_interval_slot": value.get("last_interval_slot") or value.get("last_post_slot"),
                "last_post_id": value.get("last_post_id"),
                "last_post_text": value.get("last_post_text"),
                "last_post_at": value.get("last_post_at"),
                "last_post_views": value.get("last_post_views"),
                "copied_reference_tweet_ids": value.get("copied_reference_tweet_ids") or [],
            },
        }

    # Compatibility accessors while call sites migrate.
    @property
    def niche(self) -> str:
        return self.profile.niche

    @niche.setter
    def niche(self, value: str) -> None:
        self.profile.niche = value

    @property
    def twitter_handle(self) -> str:
        return self.profile.twitter_handle

    @twitter_handle.setter
    def twitter_handle(self, value: str) -> None:
        self.profile.twitter_handle = value

    @property
    def status(self) -> str:
        return self.profile.status

    @status.setter
    def status(self, value: str) -> None:
        self.profile.status = value

    @property
    def followers(self) -> int:
        return self.profile.followers

    @followers.setter
    def followers(self, value: int) -> None:
        self.profile.followers = value

    @property
    def posts_total(self) -> int:
        return self.profile.posts_total

    @posts_total.setter
    def posts_total(self, value: int) -> None:
        self.profile.posts_total = value

    @property
    def registered_at(self) -> str | None:
        return self.profile.registered_at

    @registered_at.setter
    def registered_at(self, value: str | None) -> None:
        self.profile.registered_at = value

    @property
    def followers_when_registered(self) -> int | None:
        return self.profile.followers_when_registered

    @followers_when_registered.setter
    def followers_when_registered(self, value: int | None) -> None:
        self.profile.followers_when_registered = value

    @property
    def system_prompt(self) -> str:
        return self.voice.system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self.voice.system_prompt = value

    @property
    def personality(self) -> str:
        return self.voice.personality

    @personality.setter
    def personality(self, value: str) -> None:
        self.voice.personality = value

    @property
    def negative_semantics(self) -> list[str]:
        return self.voice.negative_semantics

    @negative_semantics.setter
    def negative_semantics(self, value: list[str]) -> None:
        self.voice.negative_semantics = value

    @property
    def twitter_oauth2_access_token_enc(self) -> str | None:
        return self.credentials.oauth2_access_token_enc

    @twitter_oauth2_access_token_enc.setter
    def twitter_oauth2_access_token_enc(self, value: str | None) -> None:
        self.credentials.oauth2_access_token_enc = value

    @property
    def twitter_oauth2_refresh_token_enc(self) -> str | None:
        return self.credentials.oauth2_refresh_token_enc

    @twitter_oauth2_refresh_token_enc.setter
    def twitter_oauth2_refresh_token_enc(self, value: str | None) -> None:
        self.credentials.oauth2_refresh_token_enc = value

    @property
    def last_interval_slot(self) -> str | None:
        return self.posting.last_interval_slot

    @last_interval_slot.setter
    def last_interval_slot(self, value: str | None) -> None:
        self.posting.last_interval_slot = value

    @property
    def last_post_id(self) -> str | None:
        return self.posting.last_post_id

    @last_post_id.setter
    def last_post_id(self, value: str | None) -> None:
        self.posting.last_post_id = value

    @property
    def last_post_text(self) -> str | None:
        return self.posting.last_post_text

    @last_post_text.setter
    def last_post_text(self, value: str | None) -> None:
        self.posting.last_post_text = value

    @property
    def last_post_at(self) -> str | None:
        return self.posting.last_post_at

    @last_post_at.setter
    def last_post_at(self, value: str | None) -> None:
        self.posting.last_post_at = value

    @property
    def last_post_views(self) -> int | None:
        return self.posting.last_post_views

    @last_post_views.setter
    def last_post_views(self, value: int | None) -> None:
        self.posting.last_post_views = value

    @property
    def copied_reference_tweet_ids(self) -> list[str]:
        return self.posting.copied_reference_tweet_ids

    @copied_reference_tweet_ids.setter
    def copied_reference_tweet_ids(self, value: list[str]) -> None:
        self.posting.copied_reference_tweet_ids = value

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"accounts/{account_id}"

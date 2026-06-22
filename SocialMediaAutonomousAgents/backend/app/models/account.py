"""Account document shape stored in RavenDB (collection Accounts).

The account's writing identity lives in `soul` (see AccountSoul). Older documents
stored a flat layout or a `voice` object; `_lift_legacy_fields` migrates both into `soul`.
"""

from typing import Literal  # correlation enum for ContrastPattern

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.models.niche import Niche


# ─────────────────────────────────────────────────────────────────────────────
# Soul defaults
# ─────────────────────────────────────────────────────────────────────────────

def default_system_prompt(niche: str) -> str:
    """Default *posting* prompt (structural composition instructions) for a niche.
    Name kept for compatibility with existing imports; it now seeds soul.posting_prompt."""
    return (
        f"Generate a post about {niche}. "
        "Open with a shocked, opinionated hook (conversational, not newsy) and keep it as one long, "
        "almost run-on sentence with commas—not a chain of short separate sentences. "
        "Post length: 150-280 characters."
    )


def default_contrast_patterns() -> list[dict]:
    """Default contrast patterns. These REPLACE the old negative_semantics list:
    each former 'avoid this' string becomes a pattern with correlation='negative'.
    Stored as plain dicts so Pydantic builds ContrastPattern instances on validation."""
    negatives = [
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
    return [{"text": t, "correlation": "negative"} for t in negatives]


def default_punctuation_rules() -> list[dict]:
    """Deterministic punctuation auto-fixes applied AFTER generation.
    Pure formatting hygiene only — NOT the old ~80 banned phrases (those are archived
    in docs/voice-banned-phrases-archive.md and intentionally not recreated here).
    `replacement: None` means 'delete the match'."""
    return [
        {"pattern": r"\s*[—–]\s*", "replacement": ", "},           # em/en dash → comma
        {"pattern": r"(?<=\w)\s*--\s*(?=\w)", "replacement": ", "},  # double hyphen between words → comma
        {"pattern": r" {2,}", "replacement": " "},                   # collapse runs of spaces
        {"pattern": r"\s+([,.!?;:])", "replacement": r"\1"},        # drop space before punctuation
        {"pattern": r",\s*,", "replacement": ","},                   # ",," → ","
        {"pattern": r"\.\s*\.", "replacement": "."},                # ".." → "."
        {"pattern": r",\s*\.", "replacement": "."},                 # ",." → "."
        {"pattern": r"^[,;:\s]+", "replacement": ""},               # strip leading punctuation/space
    ]


def format_contrast_patterns_for_prompt(patterns: "list[ContrastPattern] | list[dict] | None") -> str:
    """Render contrast patterns into a compose-prompt block, split by correlation.
    Negative → things to avoid; positive → things to lean into. Replaces
    format_negative_semantics_for_prompt(). Accepts model instances or raw dicts."""
    def _text(p) -> str:
        return (p.text if isinstance(p, ContrastPattern) else str(p.get("text", ""))).strip()

    def _corr(p) -> str:
        return p.correlation if isinstance(p, ContrastPattern) else str(p.get("correlation", "negative"))

    items = [p for p in (patterns or []) if _text(p)]
    if not items:
        items = [ContrastPattern.model_validate(d) for d in default_contrast_patterns()]

    avoid = [_text(p) for p in items if _corr(p) == "negative"]
    lean = [_text(p) for p in items if _corr(p) == "positive"]

    blocks: list[str] = []
    if avoid:
        blocks.append("Avoid these patterns and tells:\n" + "\n".join(f"- {t}" for t in avoid))
    if lean:
        blocks.append("Lean into these patterns:\n" + "\n".join(f"- {t}" for t in lean))
    return "\n\n".join(blocks)


# ─────────────────────────────────────────────────────────────────────────────
# Soul building blocks
# ─────────────────────────────────────────────────────────────────────────────

class ContrastPattern(BaseModel):
    """A writing pattern the LLM should avoid or favor.
    correlation drives how it is rendered into the prompt (see format_contrast_patterns_for_prompt)."""
    text: str
    correlation: Literal["positive", "negative"] = "negative"


class PunctuationRule(BaseModel):
    """A deterministic regex auto-fix applied to generated text.
    replacement=None deletes the match; otherwise substitutes."""
    pattern: str
    replacement: str | None = None


class AccountSoul(BaseModel):
    """The writing identity of an account: who it is and how its text is shaped."""
    model_config = ConfigDict(populate_by_name=True)

    # The account's persona / kind ("Global News Commentary", "Stock Trader", ...).
    # Loads a legacy ``niche`` key for documents that predate the rename.
    category: str = Field(default="", validation_alias=AliasChoices("category", "niche"))
    # Popular niches: scored topics the account is observed to ride. See niche_service.
    # Excluded from the voice version hash, so score changes never bump the version.
    niches: list[Niche] = Field(default_factory=list)
    # Prose describing character, likes/dislikes, reactions to people/topics, tone quirks
    # (e.g. occasional lowercase sentence starts). This is the primary LLM steering text.
    personality: str = Field(default="")
    # Structural instructions for composing a post (was AccountVoice.system_prompt).
    posting_prompt: str = Field(default="")
    # LLM guidance: avoid (negative) / lean into (positive). Replaces negative_semantics.
    contrast_patterns: list[ContrastPattern] = Field(default_factory=default_contrast_patterns)
    # Deterministic post-generation punctuation hygiene (auto-fix; never regenerate).
    punctuation_rules: list[PunctuationRule] = Field(default_factory=default_punctuation_rules)
    # Version stamp; bumps when ANY field above changes (see voice_version_service).
    voice_version_hash: str | None = None
    voice_version_seq: int = 1
    voice_version_label: str | None = "v1"


def default_soul(category: str) -> AccountSoul:
    """Fresh soul for a new account; posting_prompt is seeded from the category."""
    return AccountSoul(
        category=category or "",
        niches=[],
        personality="",
        posting_prompt=default_system_prompt(category),
        contrast_patterns=[ContrastPattern.model_validate(d) for d in default_contrast_patterns()],
        punctuation_rules=[PunctuationRule.model_validate(d) for d in default_punctuation_rules()],
    )


def _soul_from_legacy(src: dict) -> dict:
    """Build a soul dict from a legacy flat doc or legacy `voice` object.
    - posting_prompt ← system_prompt
    - personality    ← personality
    - contrast_patterns ← negative_semantics mapped to correlation='negative'
      (falls back to defaults when absent)
    - punctuation_rules ← defaults (legacy docs never had these)
    Version stamp is carried over so we don't reset history on migration."""
    neg = src.get("negative_semantics")
    contrast = (
        [{"text": s, "correlation": "negative"} for s in neg if s and str(s).strip()]
        if neg else default_contrast_patterns()
    )
    return {
        "category": src.get("category") or src.get("niche") or "",
        "niches": list(src.get("niches") or []),
        "personality": src.get("personality") or "",
        "posting_prompt": src.get("system_prompt") or src.get("posting_prompt") or "",
        "contrast_patterns": contrast,
        "punctuation_rules": src.get("punctuation_rules") or default_punctuation_rules(),
        "voice_version_hash": src.get("voice_version_hash"),
        "voice_version_seq": int(src.get("voice_version_seq") or 1),
        "voice_version_label": src.get("voice_version_label") or "v1",
    }


class AccountProfile(BaseModel):
    # category and niches moved to AccountSoul (the writing identity); legacy docs
    # that stored them on the profile are folded into the soul on load.
    twitter_handle: str = ""
    status: str = "active"
    # Soft-retire: retired accounts keep their docs (never deleted) but are excluded by
    # default from the posting scheduler and account listings. Defaults False for legacy docs.
    retired: bool = False
    followers: int = 0
    posts_total: int = 0
    # Provenance / dashboard (optional for legacy documents)
    registered_at: str | None = None
    followers_when_registered: int | None = None


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


ProvisioningStatus = Literal[
    "draft",            # persona approved, account row written, not yet provisioning
    "in_progress",      # agent is driving signup
    "awaiting_captcha", # agent paused; operator must solve FunCaptcha in the live window
    "x_account_created",# signup complete, account exists on X
    "dev_setup",        # developer console / pay-per-use billing in progress
    "complete",         # dev keys captured + stored
    "failed",
    "cancelled",
]


class ProvisioningImages(BaseModel):
    avatar_asset_id: str | None = None   # -> MediaAssetRepository.get(asset_id)
    header_asset_id: str | None = None


class AccountProvisioning(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # identity chosen during persona design (mirrors what gets typed into X)
    display_name: str = ""
    bio: str = ""
    images: ProvisioningImages = Field(default_factory=ProvisioningImages)
    persona_assigned: bool = False  # True once a designed persona fills this slot
    # live state
    status: ProvisioningStatus = "draft"
    current_page: str = ""          # PageState the agent last reported (free-text mirror)
    step_log: list[str] = Field(default_factory=list)   # human-readable breadcrumb
    error_message: str | None = None
    attempt_count: int = 0
    # outcome (non-secret identifiers only; keys/password/cookies live in AccountSecrets)
    x_user_id: str = ""
    dev_app_id: str = ""
    started_at: str | None = None
    completed_at: str | None = None


class AccountDocument(BaseModel):
    """Full account row in RavenDB. Document id: accounts/{account_id}."""

    account_id: str
    profile: AccountProfile
    # soul replaces the old `voice` object as the single writing-identity source.
    soul: AccountSoul = Field(default_factory=AccountSoul)
    posting: AccountPostingState = Field(default_factory=AccountPostingState)
    provisioning: AccountProvisioning = Field(default_factory=AccountProvisioning)

    @model_validator(mode="before")
    @classmethod
    def _lift_legacy_fields(cls, value: object) -> object:
        """Accept three shapes and normalize to {account_id, profile, soul, posting}:
          (A) already-nested NEW docs (have 'soul')         → pass through
          (B) nested docs with legacy 'voice' but no 'soul' → migrate voice → soul
          (C) old flat docs (no 'profile')                  → lift everything into groups
        """
        if not isinstance(value, dict):
            return value

        # (A)/(B): already nested (has 'profile')
        if "profile" in value:
            profile = value.get("profile") or {}
            # profile may arrive as an AccountProfile instance (e.g. when AccountDocument
            # is constructed with sub-models in upsert_profile), not a dict. Coerce so the
            # .get(...) reads below work — mirrors the soul handling just after.
            if not isinstance(profile, dict):
                profile = dict(profile)
            if "soul" not in value or not value.get("soul"):
                soul = _soul_from_legacy(value.get("voice") or {})
            else:
                soul = dict(value["soul"])
            # Older docs stored category/niches on the profile; fold them into soul.
            if not soul.get("category"):
                soul["category"] = (
                    profile.get("category") or profile.get("niche") or value.get("niche") or ""
                )
            if not soul.get("niches"):
                soul["niches"] = list(profile.get("niches") or [])
            if isinstance(profile, dict):
                for moved in ("category", "niche", "niches"):
                    profile.pop(moved, None)
            value["profile"] = profile
            value["soul"] = soul
            value.pop("voice", None)  # drop deprecated object; soul is canonical
            return value

        # (C): old flat document — lift profile/soul/posting out of top-level keys
        return {
            "account_id": value.get("account_id"),
            "profile": {
                "twitter_handle": value.get("twitter_handle") or "",
                "status": value.get("status") or "active",
                "followers": value.get("followers") or 0,
                "posts_total": value.get("posts_total") or 0,
                "registered_at": value.get("registered_at"),
                "followers_when_registered": value.get("followers_when_registered"),
            },
            "soul": _soul_from_legacy(value),  # reads system_prompt/personality/negative_semantics if present
            "posting": {
                "last_interval_slot": value.get("last_interval_slot") or value.get("last_post_slot"),
                "last_post_id": value.get("last_post_id"),
                "last_post_text": value.get("last_post_text"),
                "last_post_at": value.get("last_post_at"),
                "last_post_views": value.get("last_post_views"),
                "copied_reference_tweet_ids": value.get("copied_reference_tweet_ids") or [],
            },
        }

    # ── Soul accessors (category and niches live in the soul) ──
    @property
    def category(self) -> str:
        return self.soul.category

    @category.setter
    def category(self, value: str) -> None:
        self.soul.category = value

    @property
    def niches(self) -> list[Niche]:
        return self.soul.niches

    @niches.setter
    def niches(self, value: list[Niche]) -> None:
        self.soul.niches = value

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
    def retired(self) -> bool:
        return self.profile.retired

    @retired.setter
    def retired(self, value: bool) -> None:
        self.profile.retired = value

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

    # ── Soul accessors (kept to shield existing call sites; now back soul) ──
    @property
    def system_prompt(self) -> str:
        return self.soul.posting_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self.soul.posting_prompt = value

    @property
    def posting_prompt(self) -> str:        # canonical accessor
        return self.soul.posting_prompt

    @posting_prompt.setter
    def posting_prompt(self, value: str) -> None:
        self.soul.posting_prompt = value

    @property
    def personality(self) -> str:
        return self.soul.personality

    @personality.setter
    def personality(self, value: str) -> None:
        self.soul.personality = value

    @property
    def contrast_patterns(self) -> list[ContrastPattern]:
        return self.soul.contrast_patterns

    @contrast_patterns.setter
    def contrast_patterns(self, value: list[ContrastPattern]) -> None:
        self.soul.contrast_patterns = value

    @property
    def punctuation_rules(self) -> list[PunctuationRule]:
        return self.soul.punctuation_rules

    @punctuation_rules.setter
    def punctuation_rules(self, value: list[PunctuationRule]) -> None:
        self.soul.punctuation_rules = value

    @property
    def voice_version_hash(self) -> str | None:
        return self.soul.voice_version_hash

    @voice_version_hash.setter
    def voice_version_hash(self, value: str | None) -> None:
        self.soul.voice_version_hash = value

    @property
    def voice_version_seq(self) -> int:
        return self.soul.voice_version_seq

    @voice_version_seq.setter
    def voice_version_seq(self, value: int) -> None:
        self.soul.voice_version_seq = value

    @property
    def voice_version_label(self) -> str | None:
        return self.soul.voice_version_label

    @voice_version_label.setter
    def voice_version_label(self, value: str | None) -> None:
        self.soul.voice_version_label = value

    # NOTE: the `negative_semantics` accessor is INTENTIONALLY REMOVED.
    #       Every reader was swept to contrast_patterns/soul fields:
    #         - runner.py compose call + TickInput construction (Task 06)
    #         - account_snapshot_service.py (Task 02 addendum)
    #         - voice_version_service.py (Task 05)
    #         - account_update_service / account_repository (dict, not accessor) (03/04)

    # ── Posting-state accessors ──
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

    # ── Provisioning accessor ──
    @property
    def provisioning_status(self) -> str:
        return self.provisioning.status

    @provisioning_status.setter
    def provisioning_status(self, value: str) -> None:
        self.provisioning.status = value  # type: ignore[assignment]

    @staticmethod
    def document_id(account_id: str) -> str:
        return f"accounts/{account_id}"

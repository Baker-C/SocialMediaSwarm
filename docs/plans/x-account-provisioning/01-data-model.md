# 01 — Data Model: `AccountProvisioning` sub-document

**Touches:** `backend/app/models/account.py`

Non-secret provisioning state lives as a new sub-document on `AccountDocument`, exactly like
`AccountSoul` / `AccountPostingState`. **Secrets do NOT go here** (see `02`) — `AccountDocument` is
serialized into the public-ish `Accounts` collection and partially exposed via `account_edit_view`
and `_account_public`.

## 1. The model

Add to `account.py` near `AccountSoul` (line ~107) / `AccountPostingState` (line ~182):

```python
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
```

> `twitter_handle` already exists on `AccountProfile` — reuse it; do **not** duplicate the handle here.
> `category` / `personality` / `posting_prompt` already live on `AccountSoul` — the persona chat writes
> those through the existing soul path (`03`), not here. `AccountProvisioning` holds only what the soul
> doesn't: display name, bio, image refs, and live provisioning state.

## 2. Wire it onto `AccountDocument`

Add alongside `soul` / `posting` (line ~202):

```python
class AccountDocument(BaseModel):
    account_id: str
    profile: AccountProfile
    soul: AccountSoul = Field(default_factory=AccountSoul)
    posting: AccountPostingState = Field(default_factory=AccountPostingState)
    provisioning: AccountProvisioning = Field(default_factory=AccountProvisioning)   # NEW
```

No migration is needed: the existing `_lift_legacy_fields` `@model_validator(mode="before")`
passes unknown/missing nested keys through, so old docs load with the default-factory
`AccountProvisioning`. The one live account (`JohnJames_News`) simply gains an empty default on
next save.

## 3. Flat accessors (optional, match house style)

The model exposes ~30 flat `@property`/`@setter` proxies (e.g. `acc.twitter_handle`). Add the few
call sites will actually want:

```python
@property
def provisioning_status(self) -> str:
    return self.provisioning.status

@provisioning_status.setter
def provisioning_status(self, value: str) -> None:
    self.provisioning.status = value  # type: ignore[assignment]
```

Keep this minimal — only add accessors that have a real call site (the repo/service read
`acc.provisioning.*` directly).

## 4. Serialization

Nothing to do. The repository already centralizes (un)marshaling:
`account_to_document()` uses `model_dump(exclude_none=True)`; `document_to_account()` uses
`AccountDocument.model_validate(normalize_account_document(doc))`. The new sub-document rides along.

## 5. Tests (`tests/unit/test_account_provisioning_model.py`)

Pure-model tests, no DB:
- Default `AccountDocument(...)` has `provisioning.status == "draft"` and empty images.
- `model_validate` of a legacy doc dict **without** a `provisioning` key yields the default.
- Round-trip: `AccountDocument.model_validate(acc.model_dump(exclude_none=True))` preserves a
  populated `provisioning` (status, images, x_user_id).
- Setting `status` to an invalid literal raises `ValidationError`.

> Use the existing `tests/fixtures/account_fixtures.py` builders if present; otherwise construct a
> minimal `AccountDocument` inline as the other model tests do.

## Done when
- `AccountProvisioning` + `ProvisioningImages` defined; `provisioning` field on `AccountDocument`.
- Legacy/empty docs load with defaults (validator passthrough confirmed by test).
- No secret fields present on this model (reviewer check).
- `pytest tests/unit/test_account_provisioning_model.py` green; `py_compile` clean.

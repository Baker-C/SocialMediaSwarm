# 03 — Persona Chat → `PersonaDraft`

**Touches:** `backend/app/api/routes/persona.py` (new), `backend/app/api/routes/persona_types.py` (new)

A chat with Claude to design the account persona, returning a structured, editable spec. This is a
**near-clone of `agent_builder`** (`routes/agent_builder.py` + `agent_builder_types.py`) — same
stateless multi-turn, same SSE worker, same JSON-extraction structured output. Read that file before
implementing; we deviate only in the draft schema and the "approve" side-effects.

## 1. The Claude client reality (don't fight it)

`ClaudeClient` (`infrastructure/claude_client.py`) is **single-shot**: `messages(system, user)` and
`messages_json_dict(system, user)`. **No native multi-turn, no streaming, no tool-use/JSON mode.**
Structured output = prompt-for-JSON + brace/fence extraction (`_extract_json_object`).

We follow `agent_builder`'s proven workarounds:
- **Multi-turn:** client posts the full message history each turn; `_render_messages(history)` flattens
  it into one user string (`agent_builder.py:191`). No server session store.
- **Structured output:** `claude.messages_json_dict(system=SYSTEM, user=rendered, max_tokens=4096)` →
  `PersonaDraft.model_validate(raw or {...fallback...})`.
- **Model:** pass `ClaudeClient(model="claude-opus-4-8")` for this feature (project default per the
  claude-api skill; the configured default is sonnet). The same plain call works for opus-4-8.

> Chat is **not** token-streamed (the builder emits one whole assistant message per turn — see
> `builder.ts:23` note). That's acceptable for v1. True token streaming would require the Anthropic
> streaming API inside the worker; the SSE transport already supports per-token `emit`.

## 2. Types — `persona_types.py`

Mirror `agent_builder_types.py`. Reuse soul field names so the spec maps cleanly onto
`AccountCreateBody` / `AccountUpdateBody`.

```python
class PersonaChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class PersonaChatRequest(BaseModel):
    account_id: str                       # operator-chosen id (validated unique on approve)
    messages: list[PersonaChatMessage]    # full history, echoed each turn
    proposal: "PersonaSpec | None" = None # prior proposal echoed back (stateless)
    approve: bool = False

class PersonaSpec(BaseModel):
    """The structured identity Claude proposes; all fields operator-editable in the UI."""
    handle: str = ""            # @handle (no '@'); availability checked at signup, not here
    display_name: str = ""
    bio: str = ""
    category: str = ""          # -> AccountSoul.category
    personality: str = ""       # -> AccountSoul.personality
    posting_prompt: str = ""    # -> AccountSoul.posting_prompt
    avatar_prompt: str = ""     # -> fal image gen (04)
    header_prompt: str = ""     # -> fal image gen (04)

class PersonaDraft(BaseModel):
    reply: str                  # assistant's chat message
    spec: PersonaSpec | None = None   # present once enough is known to propose

# SSE event builders (mirror agent_builder_types.py:87-160)
def emit_assistant_message(text: str) -> dict: ...
def emit_persona_preview(spec: PersonaSpec) -> dict: ...   # right-pane review payload
def emit_images_generating() -> dict: ...
def emit_images_ready(avatar_asset_id: str, header_asset_id: str) -> dict: ...
def emit_account_written(account_id: str) -> dict: ...
def emit_validation_errors(errors: list[str]) -> dict: ...
def emit_error(message: str) -> dict: ...
def emit_done() -> dict: ...
```

Each event is `{"type": "...", ...}`; the frontend union mirrors these 1:1 (`08`).

## 3. Route — `persona.py`

```python
router = APIRouter()
claude = get_claude_client_opus()   # small helper or ClaudeClient(model="claude-opus-4-8")

SYSTEM_PROMPT = """You design X (Twitter) account personas. Converse with the operator to nail
down niche, audience, voice, name and bio. When you have enough, return JSON:
{"reply": "<message>", "spec": {"handle","display_name","bio","category","personality",
"posting_prompt","avatar_prompt","header_prompt"} | null}. Keep handle <=15 chars, alnum/underscore.
avatar_prompt/header_prompt are vivid image-gen prompts (square avatar, wide banner)."""

def _render_messages(history: list[PersonaChatMessage], proposal: PersonaSpec | None) -> str:
    # flatten like agent_builder._render_messages: role-tagged turns + the echoed proposal
    ...

def _run_turn(req: PersonaChatRequest, emit) -> None:
    if not claude.enabled:
        emit(emit_assistant_message("Claude is not configured (ANTHROPIC_API_KEY).")); return
    raw = claude.messages_json_dict(system=SYSTEM_PROMPT, user=_render_messages(req.messages, req.proposal), max_tokens=4096)
    draft = PersonaDraft.model_validate(raw or {"reply": "Tell me more about the account."})
    emit(emit_assistant_message(draft.reply))
    if draft.spec:
        emit(emit_persona_preview(draft.spec))

def _do_approve(req: PersonaChatRequest, emit) -> None:
    spec = req.proposal
    if spec is None:
        emit(emit_validation_errors(["No persona to approve."])); return
    # 1) images (04)
    emit(emit_images_generating())
    avatar_id, header_id = generate_persona_images(spec.avatar_prompt, spec.header_prompt)
    emit(emit_images_ready(avatar_id, header_id))
    # 2) write account via existing service path
    body = AccountCreateBody(account_id=req.account_id, category=spec.category,
                             twitter_handle=spec.handle, personality=spec.personality,
                             posting_prompt=spec.posting_prompt)
    apply_account_create(body)                       # raises AccountAlreadyExistsError -> 409 mapping
    # 3) provisioning sub-doc (identity + image refs + status=draft)
    acc = repo.load(req.account_id)
    acc.provisioning.display_name = spec.display_name
    acc.provisioning.bio = spec.bio
    acc.provisioning.images.avatar_asset_id = avatar_id
    acc.provisioning.images.header_asset_id = header_id
    acc.provisioning.status = "draft"
    repo.save(acc)
    emit(emit_account_written(req.account_id))

@router.post("/persona/chat")
async def persona_chat(req: PersonaChatRequest, request: Request):
    handler = _do_approve if req.approve else _run_turn
    # SSE worker pattern (05 §SSE / force_post.py:42-91); buffered fallback if no text/event-stream Accept
    ...
```

> **Image-asset fields on `AccountCreateBody`:** the create body doesn't carry avatar/header ids
> today. Rather than widen it, we write images via the `AccountProvisioning` sub-doc on the loaded
> account (step 3 above) — surgical, no change to `account_create_service`. Confirm `AccountCreateBody`
> field names (`twitter_handle`, `personality`, `posting_prompt`, `category`) against
> `account_create_service.py:13` when wiring; adjust to whatever it actually accepts, and use
> `apply_account_update` for any field the create body ignores (the builder does exactly this at
> `agent_builder.py:237`).

## 4. Register the router

`main.py`: add `persona` to the `from app.api.routes import (...)` tuple (line ~13) and
`app.include_router(persona.router, prefix="/api", tags=["persona"], dependencies=_auth)` in the
auth-gated block (line ~195).

## 5. Tests (`tests/unit/test_persona_routes.py`)

- **Chat turn:** inject a fake Claude returning a JSON dict; `TestClient` POST `/api/persona/chat`
  (buffered fallback, no SSE header) → assert events include `assistant_message` + `persona_preview`
  with the parsed spec. Patch the module-level `claude` (`monkeypatch.setattr(persona_routes, "claude", FakeClaude())`).
- **Approve:** patch `generate_persona_images` to return `("a1","h1")`, patch `repo`/`apply_account_create`;
  assert `account_written` emitted and `repo.save` called with `provisioning.images.avatar_asset_id == "a1"`.
- **Duplicate id:** `apply_account_create` raising `AccountAlreadyExistsError` surfaces as a 409 (route
  error mapping) or an `emit_error` in the stream — pick one and assert it.
- `PersonaDraft.model_validate({})` falls back without raising (defensive parse).

## Done when
- `/api/persona/chat` returns a validated `PersonaDraft` per turn and a `persona_preview` once a spec exists.
- Approve generates images, writes the account + `AccountProvisioning(status="draft")`, emits `account_written`.
- Router registered under auth; tests green.

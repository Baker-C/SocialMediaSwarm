# Task 10 — Conversational Agent-Builder API (backend)

> **Status:** Ready to implement. Authored cold from a verified read of the live SSE/force-post pattern, the Claude client, the soul/account models, and the sibling spec/catalog/validator/compiler docs. This slice has zero open questions **within its own scope**. The catalog-API seam is settled to doc 03's `ToolCatalog` object (§3.2/§3.3). Two items live in *other* docs and are noted in §10: (a) doc 11's frontend client must adopt THIS doc's `POST /api/agent-builder/chat` contract (its placeholder shape is superseded — flagged in StructuredOutput); (b) the frontend's pipeline **read** routes are owned by **doc 14** (per CC-11), sequenced before doc 11 — not this doc.
>
> **Sibling-doc numbering (canonical, by filename):** tool catalog = **doc 03**; spec model + versioning = **doc 04**; validator + compiler = **doc 05**; ACT-tail tools = **doc 06**; interpreter wiring = **doc 07**; step trace = **doc 08**; self-rewrite = **doc 09**; frontend = **doc 11**.
> **Scope:** Backend only. ONE new route module — `app/api/routes/agent_builder.py` — plus a small Pydantic request/event-shape module it owns, and its router registration in `main.py`. NO tool code is written (the builder only WIRES + CONFIGURES existing catalog tools). NO new persistence model is defined here (it writes existing `PipelineSpecDocument` via the doc-04 repository and edits the existing `AccountSoul` via the existing services).
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB; in-process APScheduler).
> **DB reality:** one account today — `JohnJames_News`. The builder typically *edits* that account's pipeline spec / soul; provisioning a brand-new account is the same flow with a different terminal write (`apply_account_create` instead of an in-place soul edit).

This doc builds the **conversational front door** of the Interpreter: a chat endpoint that holds the tool catalog + soul schema + seed-spec examples in context, lets the user describe an account in prose, has Claude draft a `PipelineSpecDocument` (and optional soul edits) as JSON, runs the existing **pure** `validate_spec` against it, streams structured errors back into the chat for repair on failure, renders a mermaid diagram of the compiled spec on success, and — only on explicit user approval — writes the spec (champion/challenger) and bumps the soul if it was edited.

The builder **never executes a pipeline** and **never writes tool code**. It is a wiring console.

---

## 1. Why this exists

Docs 03/04/05 made the pipeline editable *data* and gave us the machinery to validate and compile that data — but the only way to author a spec today is `scripts/seed_pipeline_spec.py` (a one-time export) or hand-editing JSON in RavenDB Studio. There is no human-friendly way to say "make an account that reacts to AI-policy news with a dry, contrarian voice" and get a validated, diagrammed, ready-to-activate pipeline + soul.

This endpoint is that way. It is the **BUILD** entry point of the Interpreter loop (MEASURE → LEARN → BUILD → RUN). It reuses three things verbatim:

1. **The force-post SSE pattern** (`app/api/routes/force_post.py:42-91`) — a worker in a thread-pool executor feeding an `asyncio.Queue`, the route yielding `data: {json}\n\n` frames. The builder is a multi-turn variant of the same shape.
2. **`ClaudeClient`** (`app/infrastructure/claude_client.py:40-98`) — specifically `messages_json_dict(system=…, user=…, max_tokens=…)` which already extracts a JSON object from a fenced/braced model reply (`_extract_json_object`, lines 17-37). The builder's "draft a spec" step is exactly this call.
3. **The pure `validate_spec` + `compile_spec`** (doc 05) and the **tool catalog** (doc 03) — the builder calls them; it does not reimplement any checking.

**The load-bearing posture (verified against the architecture brief):** the builder WIRES + CONFIGURES existing catalog tools. It can select/order tools and set the *literal*-origin config the catalog marks proposable. Per doc 03 §4.3a/§6 (reconciled): the **only** config knobs a real spec sets today are two integers — `top_n` (`deterministic.reference_rank`) and `max_results_per_query` (`data.search_fetch`). The four soul-derived compose fields (`account_posting_prompt`/`account_personality`/`contrast_patterns`/`punctuation_rules`) are `config_origin=="literal"` on the *legacy* `llm.compose_timeline_post` leaf, but that leaf is **wrapped internally by the coarse `compose_until_safe` ACT tool** (doc 06), which binds those fields from the account soul and exposes **no proposable config** to a spec — so the builder steers them through a `soul_edit` (§6.2), not through spec config. The builder cannot touch injected deps, runtime values, wired artifacts, or the non-bypassable cost/guardian invariants — and it never authors a new tool. The validator is the gate that enforces this; the builder just routes its verdict back into the chat.

---

## 2. What this doc deliberately does NOT do

- **Execute or test-run a pipeline.** No `run_account_pipeline`, no force-post, no tick. The deliverable is a *validated, persisted spec* + optional soul edit; running it is the scheduler's job (or a separate force-post the user triggers afterward).
- **Define the spec/catalog/validator/soul models.** Those are owned by docs 03/04/05 and the soul-pipeline plan. This doc *imports and calls* them. Every shared symbol is pinned in §3 with its owning doc.
- **Persist the conversation.** The chat is stateless server-side: each turn the client posts the full message history back (mirrors how `force_post` recomputes per request). No `ConversationDocument`, no session store. See Decision Defense.
- **Build a frontend.** The React chat UI + mermaid render is a sibling frontend task; this doc defines the exact request/response/event shapes it will consume and stops there.
- **Promote a challenger.** Promotion (`promote_challenger`, doc 04 §6c) is a separate operator action. The builder writes a `champion` (new account) or a `challenger` (editing a live account) and tells the user which; flipping a challenger live is out of scope.

---

## 3. Shared-type contracts this slice depends on (owned elsewhere)

These are the **minimum** members the builder reads/calls. If an owning doc lands a different name, the single adapter point is §3.6.

### 3.1 `PipelineSpecDocument` + `StepSpec` + `CompositeSpec` — **doc 04** (`app/models/pipeline_spec.py`)

Verified shape (doc 04 §3b). The builder constructs these from Claude's JSON and passes them to `validate_spec`/`compile_spec`/`PipelineSpecRepository.save`:

```python
class StepSpec(BaseModel):
    kind: Literal["step"] = "step"
    id: str
    tool_id: str
    reads: list[str] = []          # ArtifactKey .value strings
    writes: list[str] = []
    reads_optional: list[str] = []
    config: dict = {}              # proposable config ONLY
    purpose: str = ""

class CompositeSpec(BaseModel):
    kind: Literal["parallel", "chain"]
    id: str
    children: list["StepSpec | CompositeSpec"] = []
    purpose: str = ""

class PipelineSpecDocument(BaseModel):
    account_id: str
    steps: list[StepSpec | CompositeSpec] = []
    status: Literal["champion", "challenger"] = "champion"
    parent_hash: str | None = None
    version_hash: str | None = None
    version_seq: int = 1
    version_label: str | None = "v1"
    @staticmethod
    def document_id(account_id: str, status: str = "champion") -> str: ...
```

Read/used here: model construction from a dict (`PipelineSpecDocument.model_validate(draft_dict)`), `default_pipeline_spec(account_id)` (doc 04 §3c — the baseline shown to Claude as a worked example), and `PipelineSpecRepository().save(spec)` / `.load(account_id, status)` (doc 04 §6b).

### 3.2 The tool catalog — **doc 03** (`app/pipeline/spec/catalog.py` + `app/models/tool_catalog.py`)

Verified shape (doc 03 §5, reconciled per **CC-1**). Doc 03 is the **catalog owner**; its public API is:

```python
def get_tool_catalog() -> ToolCatalog: ...                   # CC-1: the ONLY catalog factory
def get_tool(tool_id: str) -> ToolCatalogDocument | None: ...
def tool_catalog_hash() -> str: ...

class ToolCatalog:                                           # CC-1: the catalog OBJECT (not a raw list)
    def get(self, tool_id: str) -> ToolCatalogDocument | None: ...
    def __contains__(self, tool_id: str) -> bool: ...
    def __iter__(self): ...                                  # CC-1: iterable (yields ToolCatalogDocument)
    def all(self) -> list[ToolCatalogDocument]: ...
    def run_for(self, tool_id: str): ...                     # CC-1: bound run callable (unused here)

class ToolCatalogDocument(BaseModel):
    tool_id: str
    kind: str
    purpose: str
    source: str | None
    prompt_stem: str | None
    output_model: str | None
    reads: list[str] | None        # fixed reads (ACT tools), or None when dynamic
    writes: list[str] | None       # fixed writes, or None when dynamic (store_key)
    parameters: list[ToolParameter]
    # CC-2: NO invariant_tool/TOOL_INVARIANT field — the validator detects required
    # structure (a SAFETY_VERDICT writer + exactly one terminal PUBLISHED_POST writer)
    # purely from artifacts. The builder never reads such a flag.
    @property
    def proposable_params(self) -> list[ToolParameter]: ...   # config_origin == "literal"
```

Per **CC-1**, `get_tool_catalog()` is the **single** catalog factory and the `ToolCatalog` it returns is iterable. The builder uses that one object three ways: it **iterates** it (or `.all()`) to render the **catalog block** in the system prompt (§5.2), passes it as the `catalog` argument to `validate_spec`/`compile_spec` (§3.6), and calls `tool_catalog_hash()` to stamp which catalog the draft was validated against (informational, surfaced in the approve response). There is **no separate `build_tool_catalog()` factory** in this doc — the prompt block and the validate/compile arg are the same object.

### 3.3 The validator + compiler — **doc 05** (`app/pipeline/spec/`)

Verified shape (doc 05 §5.2, §6). Both pure:

```python
def validate_spec(doc: PipelineSpecDocument, catalog: ToolCatalog) -> ValidationReport: ...
def compile_spec(doc: PipelineSpecDocument, *, catalog: ToolCatalog | None = None) -> tuple[Step, ...]: ...

class ValidationError(BaseModel):
    code: str
    step_id: str | None
    artifact: str | None = None
    detail: str = ""

class ValidationReport(BaseModel):
    ok: bool
    errors: list[ValidationError]
    def codes(self) -> list[str]: ...
```

> **Catalog-API reconciliation (SETTLED by CC-1 — the builder uses the `ToolCatalog` object).** Per **CC-1** the catalog is a **`ToolCatalog` object** (`.get(tool_id)` / `__contains__` / iterable / `run_for`), the **only** factory is `get_tool_catalog()` (in `app/pipeline/spec/catalog.py`), and the name `build_catalog()` is removed everywhere. `validate_spec(doc, catalog)` and `compile_spec(doc, catalog=get_tool_catalog())` accept that object. So `_load_catalog()` (§3.6) returns `get_tool_catalog()`, and the prompt block iterates the same object — there is no second `build_tool_catalog()` factory call in this doc. This is the same object every other caller passes: doc 04 §6c's `promote_challenger`, doc 09's self-rewrite, doc 05's validator/compiler, and the runner (doc 07). (Where doc 05's prose still describes accepting a raw list, or doc 09 still names `build_catalog()`, **CC-1 overrides** — those are sibling-doc lag, not a contract this doc honors. No code in *this* doc changes regardless: `_load_catalog()` is the single adapter point.)

### 3.4 The mermaid renderer — **REUSED verbatim** (`app/pipeline/types/flow.py:127-138`)

```python
def artifact_graph_mermaid(steps: Sequence[Step]) -> str: ...
```

Verified: takes a `Sequence[Step]` (the exact output type of `compile_spec`), returns a `flowchart LR` mermaid string by drawing each artifact's first-writer → every reader. The builder calls `artifact_graph_mermaid(compile_spec(spec))` to produce the diagram it streams on a passing validation. **No new diagram code.** (The frontend renders mermaid at runtime; constraint: "React CRA, no build-time codegen; runtime mermaid".)

### 3.5 Soul edit + account write — **REUSED verbatim** (soul-pipeline plan)

- `AccountRepository.load(account_id) / .save(account)` (`app/services/account_repository.py:108-121`). `save()` already calls `bump_voice_version_if_needed(account, previous_hash=account.voice_version_hash)` (line 116) — **so editing a soul field and calling `repo.save` auto-bumps the voice version and archives a `VoiceRevisionDocument`.** The builder does NOT call the version service directly; it edits the soul fields and saves. (Verified `voice_version_service.bump_voice_version_if_needed`, lines 48-104, and `AccountRepository.save`.)
- `AccountUpdateBody` + `apply_account_update(account_id, body, repo=…)` (`app/services/account_update_service.py:20-128`, verified) — the existing soul-field editor (`category` [via `niche` alias], `posting_prompt`, `personality`, `contrast_patterns`, `punctuation_rules`). **All five `BuilderSoulEdit` fields (§6.2) map 1:1 onto `AccountUpdateBody`** — `category` IS a field on the body (verified `account_update_service.py:25-27`, with the `niche` alias; handled at `:90-92`), so the builder maps it through with no workaround. Note `apply_account_update` calls `repo.save(acc)` itself (`:127`), and `repo.save` auto-bumps the voice version (`account_repository.py:116`). The builder reuses this for the soul-edit path so it goes through the same validation/normalization the dashboard PATCH uses. (`AccountUpdateBody.contrast_patterns`/`punctuation_rules` are typed `list[ContrastPattern]`/`list[PunctuationRule]`; Pydantic validates the builder's raw-dict lists into those models on construction — see §6.2's `_update_body`.)
- `AccountCreateBody` + `apply_account_create(body, repo=…)` (`app/services/account_create_service.py:35-71`) — for the new-account path (provision profile + soul, OAuth connected separately).
- Soul schema for the prompt: `AccountSoul` fields and the default factories `default_contrast_patterns()` / `default_punctuation_rules()` / `default_system_prompt(niche)` (`app/models/account.py:18-141`). These are rendered into the system prompt as the **soul schema block** (§5.2).

### 3.6 The adapter point

All sibling-doc symbol access is funneled through small helpers at the top of `agent_builder.py`, so a rename in docs 03/04/05 is a localized change:

```python
from app.pipeline.spec.catalog import get_tool_catalog, tool_catalog_hash   # doc 03 — CC-1: one factory
from app.pipeline.spec import validate_spec, compile_spec                                       # doc 05 (re-exported)
from app.pipeline.types.flow import artifact_graph_mermaid                                       # flow.py:127
from app.models.pipeline_spec import default_pipeline_spec                                       # doc 04
from app.services.pipeline_spec_repository import PipelineSpecRepository                         # doc 04

def _load_catalog():                      # -> ToolCatalog object (CC-1: the only factory)
    return get_tool_catalog()

def _catalog_tools():                     # -> list[ToolCatalogDocument] for prompt rendering (§5.2)
    return _load_catalog().all()          # CC-1: iterate the one object; no build_tool_catalog()

def _validate(spec) -> "ValidationReport":          # doc 05 — passes the catalog object
    return validate_spec(spec, _load_catalog())

def _compile(spec) -> tuple["Step", ...]:           # doc 05 — passes the catalog object
    return compile_spec(spec, catalog=_load_catalog())

def _mermaid(spec) -> str:                # artifact_graph_mermaid(_compile(spec))  (flow.py:127)
    return artifact_graph_mermaid(_compile(spec))

def _baseline_spec(account_id):           # default_pipeline_spec(account_id)  (doc 04 §3c)
    return default_pipeline_spec(account_id)

def _save_spec(spec) -> str:              # PipelineSpecRepository().save(spec); returns doc_id (doc 04)
    repo = PipelineSpecRepository()
    repo.save(spec)                       # in-place: bumps version, archives a revision
    return PipelineSpecDocument.document_id(spec.account_id, spec.status)
```

> **`PipelineSpecRepository.save` returns `None`** (doc 04 §6b — it mutates the passed `spec` in place via `bump_pipeline_version_if_needed`, then PUTs). So `_save_spec` computes the doc id itself from `spec.account_id`/`spec.status` (the same id `save` writes) and the post-save `version_label` is read directly off `spec.version_label` — there is no separate re-read (see §7.3).

---

## 4. The endpoint at a glance

```
POST /api/agent-builder/chat        (Accept: text/event-stream)   ← the conversational driver
  body: BuilderChatRequest { account_id, mode, messages[], approve? }
        │
        │  (mirrors force_post.py: worker() in run_in_executor feeding an asyncio.Queue;
        │   route yields  data: {json}\n\n  frames from the queue)
        ▼
  worker(): one turn of the builder state machine
        │
        ├─ if approve == True:  re-draft is skipped; the LAST assistant-proposed spec
        │   (echoed back in the request, see §6.1) is re-validated, then WRITTEN:
        │     - new account  → apply_account_create(...) then _save_spec(champion)
        │     - edit account → soul edit via apply_account_update (if soul changed)
        │                       then _save_spec(challenger)
        │     emits  spec_written  then  done.
        │
        └─ else (a normal turn):
             1. build system prompt = ToolCatalog block + AccountSoul schema block
                + baseline seed-spec example  (held in context every turn)
             2. claude.messages_json_dict(system, user=<rendered messages>)  → draft JSON
             3. parse draft → { reply, spec?, soul_edit? }   (BuilderDraft, §6.2)
             4. emit  assistant_message(reply)
             5. if spec present:
                  report = _validate(spec)
                  if not report.ok:  emit  validation_errors(report.errors)   ← repair loop
                  else:              emit  spec_preview(mermaid, spec, catalog_hash)
             6. emit  done   (turn complete; client awaits next user message or sends approve)
```

Every step that can fail emits a typed event and the worker continues to `done`; a hard exception emits `error` then `done` (same fault posture as `force_post`).

---

## 5. The system prompt — what is held in context every turn

The builder's leverage is entirely in its system prompt. It is **rebuilt per turn** (cheap; pure string assembly over `_catalog_tools()` — i.e. the single `get_tool_catalog()` object, CC-1 — plus the soul defaults) and has three blocks.

### 5.1 Role + hard rules (static prose)

States, verbatim in the prompt:
- You WIRE + CONFIGURE existing tools. You never invent a tool or write tool code.
- You may only set config keys the catalog marks proposable (`config_origin == "literal"`). Setting anything else will be rejected.
- Every pipeline must contain a step that produces a safety verdict (writes `safety_verdict`) and end in **exactly one terminal** step that publishes (writes `published_post`) — per **CC-2** the validator detects these from the artifacts written, not from any tool flag, so you satisfy them by including `compose_until_safe` and a terminal `publish_post`. These are non-negotiable invariants you cannot remove.
- When you propose a spec, emit it as JSON in the exact `BuilderDraft` shape (§6.2). When you are only chatting/clarifying, emit `spec: null`.

### 5.2 Live data blocks (rebuilt each turn)

- **Tool catalog block** — for each `ToolCatalogDocument` from `_catalog_tools()` (the single `get_tool_catalog()` object, CC-1): `tool_id`, `kind`, `purpose`, `writes` (or "dynamic"), and the **proposable** params only (`d.proposable_params`: name, type, default). Injected/runtime/wired params are deliberately omitted so Claude never proposes them. This is the honest surface from doc 03 §6.
- **Soul schema block** — the `AccountSoul` field list (`category`, `personality`, `posting_prompt`, `contrast_patterns: [{text, correlation}]`, `punctuation_rules: [{pattern, replacement}]`) with the default factories shown as examples (`default_contrast_patterns()`, `default_punctuation_rules()`). Tells Claude what a `soul_edit` may contain.
- **Seed-spec example block** — `default_pipeline_spec(account_id).model_dump(mode="json")` rendered as the canonical worked example of a **valid** `steps` tree. Per doc 04 §7 (settled), this baseline is the full **SENSE+ACT graph (10 leaves)**: the 4 top-level SENSE leaves (`load_account_bundle`, `fetch_search_references`, `collect_external_references`, `fetch_own_post_history`) + the `summarize_for_compose` parallel-of-chains (4 more leaves) + the two ACT-tail leaves `compose_until_safe` (writes `COMPOSED_POST`+`SAFETY_VERDICT`) and `publish_post` (writes `PUBLISHED_POST`, terminal). The ACT tail is what makes the example pass the validator's R6 (terminal `PUBLISHED_POST`) and R7 (safety/publish invariants) — a SENSE-only 8-leaf baseline would NOT validate, so the few-shot **must** be the 10-leaf form. This is the single most load-bearing few-shot: it shows the exact id/composite/reads/writes vocabulary the validator expects, so Claude's drafts match the dotted-id contract `flowGraph.ts` couples to (doc 05 §6.1) and already contain the required invariant-bearing tools.

### 5.3 The user message

The rendered conversation: each `BuilderChatMessage` in `messages[]` flattened to `role: text`. The builder passes the whole history every turn (stateless server) so Claude sees prior drafts and the validation errors that were streamed back — that is the repair loop's memory. (See §6.1 for why errors are echoed into the next user turn.)

---

## 6. Request / response / event shapes (this doc OWNS these)

New module `app/api/routes/agent_builder_types.py` (kept beside the route, mirroring how `pipeline_progress.py` owns `PipelineProgressEvent` for `force_post`). All Pydantic so they JSON-dump straight into SSE frames.

### 6.1 Request

```python
from typing import Literal
from pydantic import BaseModel, Field

class BuilderChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    # When role == "assistant" and this message proposed a spec, the client echoes
    # the proposed draft + any proposed soul edit + the validation errors it received
    # back here, so the next turn's prompt (and an approve) can reference the exact
    # prior proposal without a server-side session store. None for plain chat turns.
    proposed_spec: dict | None = None
    proposed_soul_edit: dict | None = None   # echoed from spec_preview.soul_edit (§6.3)
    validation_errors: list[dict] | None = None

class BuilderChatRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=500)
    # "create" provisions a new account; "edit" stages a challenger on a live account.
    mode: Literal["create", "edit"] = "edit"
    messages: list[BuilderChatMessage] = Field(default_factory=list)
    # When True, this turn does NOT re-draft; it writes the most recent assistant
    # proposed_spec (re-validated first). The client sets approve=True after the user
    # clicks "Approve & write".
    approve: bool = False
```

> **Why the client echoes `proposed_spec`/`validation_errors` (Decision Defense).** The server holds no conversation. To repair or approve, the next turn needs the prior draft. Rather than a session document (a second source of truth with its own lifecycle), the client — which already has the streamed `spec_preview`/`validation_errors` payloads — echoes them back in the message history. This is the same statelessness `force_post` relies on (it recomputes everything per request) and keeps the builder a pure function of its request. The approve path reads `messages[-1].proposed_spec` (the last assistant proposal); if absent, it emits an `error` ("nothing to approve") and `done`.

### 6.2 The draft Claude returns (parsed from `messages_json_dict`)

```python
class BuilderSoulEdit(BaseModel):
    # Any subset; omitted fields are left untouched. Maps 1:1 onto AccountUpdateBody.
    posting_prompt: str | None = None
    personality: str | None = None
    contrast_patterns: list | None = None
    punctuation_rules: list | None = None
    category: str | None = None

class BuilderDraft(BaseModel):
    # Human-readable assistant turn (always present).
    reply: str = ""
    # A full PipelineSpecDocument-shaped dict, or None when Claude is only chatting.
    # Parsed into PipelineSpecDocument via model_validate before validation.
    spec: dict | None = None
    # Optional soul changes proposed alongside the spec.
    soul_edit: BuilderSoulEdit | None = None
```

`claude.messages_json_dict(...)` returns a `dict | None`; the worker does `BuilderDraft.model_validate(draft or {})`. A `None`/unparseable reply degrades to `BuilderDraft(reply="<fallback ask-to-rephrase>", spec=None)` and emits an `assistant_message` + `done` — never a 500.

### 6.3 SSE events streamed back (the `type` discriminant)

Each frame is `data: {json}\n\n`; `json` always has a `type`. This is the exact contract the frontend chat consumes (it parses `data:` lines exactly like `streamForcePost` does for force-post — same wire format).

| `type` | Payload fields | When |
|---|---|---|
| `assistant_message` | `text` | Claude's prose reply for this turn (always, before any spec handling). |
| `validation_errors` | `errors: list[{code, step_id, artifact, detail}]` | Draft had a spec but `validate_spec` failed. The repair signal. |
| `spec_preview` | `mermaid: str`, `spec: dict`, `catalog_hash: str`, `soul_edit: dict \| None` | Draft had a spec and it validated. The approvable proposal. |
| `spec_written` | `spec_doc_id: str`, `status: "champion" \| "challenger"`, `version_label: str`, `soul_bumped: bool`, `account_id: str` | The approve path persisted the spec (and optionally bumped the soul). |
| `error` | `message: str` | A hard failure (Claude client raised, write raised, nothing-to-approve). Terminal for the turn. |
| `done` | — (`{"type":"done"}`) | Always the last frame of every turn (mirrors `force_post`'s `None` sentinel that closes the stream). |

> `validation_errors.errors` is `[e.model_dump() for e in report.errors]` — the `ValidationError` model serialized straight through (doc 05 §5.2 made it Pydantic precisely so it can ride an SSE/JSON payload). No reshaping.

### 6.4 Non-SSE fallback

Like `force_post`, when `Accept` is not `text/event-stream` the route runs one turn synchronously (`await asyncio.to_thread(_run_builder_turn, req, events.append)`, collecting into a local `events: list[dict]`) and returns the **collected** events as a JSON list `{"events": [...]}` (terminated by `{"type":"done"}`, appended by the route — see §7.1). Same worker, buffered instead of streamed. Keeps the endpoint testable with a plain POST and usable without SSE.

---

## 7. File-by-file plan

| File | CHANGED / NEW / REUSED | One-line role |
|---|---|---|
| `app/api/routes/agent_builder.py` | **NEW** | The SSE chat route + the `_run_builder_turn` state machine (draft → validate → preview, or approve → write). |
| `app/api/routes/agent_builder_types.py` | **NEW** | `BuilderChatRequest`/`BuilderChatMessage`/`BuilderDraft`/`BuilderSoulEdit` + the SSE event builders (§6). |
| `app/main.py` | **CHANGED** | Import `agent_builder` and `include_router(agent_builder.router, prefix="/api", tags=["agent-builder"], dependencies=_auth)` (mirrors line 183). |
| `tests/unit/test_agent_builder.py` | **NEW** | Turn state machine with a **fake Claude** (no network): draft-invalid→`validation_errors`, draft-valid→`spec_preview`, approve→`spec_written`; non-SSE buffered path. |
| `app/infrastructure/claude_client.py` | **REUSED** | `get_claude_client()` + `messages_json_dict(system, user, max_tokens)` — the draft call. Unchanged. |
| `app/api/routes/force_post.py` | **REUSED (pattern)** | The SSE worker/queue/`data:` frame shape copied (`:42-91`). Not imported; pattern mirrored. |
| `app/pipeline/spec/catalog.py` (doc 03) | **REUSED** | `get_tool_catalog()` (CC-1: the one `ToolCatalog` object — iterated for the prompt block AND passed to validate/compile) + `tool_catalog_hash()` (stamp). |
| `app/pipeline/spec/validator.py` + `compiler.py` (doc 05) | **REUSED** | `validate_spec`, `compile_spec` — the gate + lowering. |
| `app/pipeline/types/flow.py` | **REUSED** | `artifact_graph_mermaid(compile_spec(spec))` for the diagram (`:127`). |
| `app/models/pipeline_spec.py` + `app/services/pipeline_spec_repository.py` (doc 04) | **REUSED** | `PipelineSpecDocument`, `default_pipeline_spec`, `PipelineSpecRepository.save/load`. |
| `app/services/account_repository.py` / `account_update_service.py` / `account_create_service.py` | **REUSED** | Soul edit + new-account write; `save()` auto-bumps the voice version (`:116`). |

### 7.1 The route (shape; mirrors `force_post.py:42-91`)

```python
# app/api/routes/agent_builder.py
router = APIRouter()

async def _sse_builder(req: BuilderChatRequest):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            _run_builder_turn(req, emit)          # emits typed events; never raises out
        except Exception as exc:                  # last-resort guard (mirrors force_post)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
            loop.call_soon_threadsafe(queue.put_nowait, None)   # sentinel closes the stream

    loop.run_in_executor(None, worker)
    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item, default=str)}\n\n"

@router.post("/agent-builder/chat")
async def agent_builder_chat(req: BuilderChatRequest, request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        return StreamingResponse(_sse_builder(req), media_type="text/event-stream")
    events: list[dict] = []
    await asyncio.to_thread(_run_builder_turn, req, events.append)   # buffered, same worker
    events.append({"type": "done"})
    return {"events": events}
```

> `worker()` runs in the executor thread; the Claude call, validation, compilation, and RavenDB writes are all **synchronous** (matching the rest of the system — the APScheduler threadpool model). The `emit` callback marshals back to the loop thread via `call_soon_threadsafe`, exactly as `force_post`'s `emit` does (`force_post.py:47-48`). No async leaks into the builder logic; `_run_builder_turn(req, emit)` is plain sync code and is the unit-tested surface.

### 7.2 `_run_builder_turn(req, emit)` — the state machine

```python
def _run_builder_turn(req: BuilderChatRequest, emit) -> None:
    if req.approve:
        _do_approve(req, emit)         # §7.3
        return

    system = _build_system_prompt(req.account_id)      # §5
    user = _render_messages(req.messages)              # role: text, including echoed errors
    claude = get_claude_client()
    if not claude.enabled:                              # no API key → honest message, no crash
        emit(_assistant_message("Agent builder needs ANTHROPIC_API_KEY configured."))
        return

    raw = claude.messages_json_dict(system=system, user=user, max_tokens=4096)
    draft = BuilderDraft.model_validate(raw or {"reply": _REPHRASE})
    emit(_assistant_message(draft.reply or _REPHRASE))

    if draft.spec is None:
        return                                          # pure chat/clarify turn

    try:
        spec = PipelineSpecDocument.model_validate({**draft.spec, "account_id": req.account_id})
    except ValidationError as exc:                      # malformed JSON shape, not a spec rule
        emit(_validation_errors([{"code": "spec_parse_error", "step_id": None,
                                  "artifact": None, "detail": str(exc)}]))
        return

    report = _validate(spec)
    if not report.ok:
        emit(_validation_errors([e.model_dump() for e in report.errors]))
        return

    mermaid = _mermaid(spec)                            # artifact_graph_mermaid(compile_spec(spec))
    emit(_spec_preview(mermaid=mermaid, spec=spec.model_dump(mode="json"),
                       catalog_hash=tool_catalog_hash(),
                       soul_edit=draft.soul_edit.model_dump(exclude_none=True) if draft.soul_edit else None))
```

Two things are forced onto the draft regardless of what Claude returns: `account_id` (from the request, never Claude — Claude must not be able to retarget another account) and the `status` is normalized in the write path (§7.3), not trusted from the draft.

### 7.3 `_do_approve(req, emit)` — the only mutating path

```python
def _do_approve(req: BuilderChatRequest, emit) -> None:
    proposal = req.messages[-1].proposed_spec if req.messages else None
    if not proposal:
        emit({"type": "error", "message": "Nothing to approve — propose a spec first."})
        return
    spec = PipelineSpecDocument.model_validate({**proposal, "account_id": req.account_id})

    # Re-validate before writing — never persist an unvalidated spec, even on approve.
    report = _validate(spec)
    if not report.ok:
        emit(_validation_errors([e.model_dump() for e in report.errors]))
        return

    soul_edit = _last_soul_edit(req.messages)           # echoed alongside proposed_spec
    soul_bumped = False

    if req.mode == "create":
        apply_account_create(_create_body(req.account_id, soul_edit))   # provisions profile+soul
        spec.status = "champion"
        soul_bumped = soul_edit is not None              # create stamps v1 soul anyway
    else:  # edit
        if soul_edit is not None:
            apply_account_update(req.account_id, _update_body(soul_edit))  # save() auto-bumps voice
            soul_bumped = True
        spec.status = "challenger"
        spec.version_hash = None                         # force a fresh bump on save

    doc_id = _save_spec(spec)                            # PipelineSpecRepository().save → versions+archives
    # save() bumps the version IN PLACE on `spec` (doc 04 §6b mutates via
    # bump_pipeline_version_if_needed), so the label is already on spec.version_label —
    # no re-read from Raven is needed.
    emit({"type": "spec_written", "spec_doc_id": doc_id, "status": spec.status,
          "version_label": spec.version_label, "soul_bumped": soul_bumped,
          "account_id": req.account_id})
```

The three small helpers `_do_approve` uses, defined alongside it (all pure, no I/O beyond the existing services):

```python
def _last_soul_edit(messages: list[BuilderChatMessage]) -> BuilderSoulEdit | None:
    """The soul_edit echoed on the last assistant proposal, if any. The client echoes
    it as proposed_soul_edit on the same message that carries proposed_spec (§6.1).
    Walk from the end so the most recent proposal wins."""
    for m in reversed(messages):
        if m.role == "assistant" and m.proposed_spec is not None:
            return BuilderSoulEdit.model_validate(m.proposed_soul_edit) if m.proposed_soul_edit else None
    return None

def _update_body(soul_edit: BuilderSoulEdit) -> AccountUpdateBody:
    """Map the echoed soul edit 1:1 onto the existing PATCH body (§3.5). Only the set
    fields ride through; AccountUpdateBody leaves omitted fields untouched."""
    return AccountUpdateBody(**soul_edit.model_dump(exclude_none=True))

def _create_body(account_id: str, soul_edit: BuilderSoulEdit | None) -> AccountCreateBody:
    """Map the echoed soul edit onto the new-account body. account_id is forced from the
    request; category/posting_prompt/etc. come from the edit (all defaulted if absent)."""
    fields = soul_edit.model_dump(exclude_none=True) if soul_edit else {}
    return AccountCreateBody(account_id=account_id, **fields)
```

> **Why the soul edit rides as its own echoed field (`proposed_soul_edit`).** A spec proposal and a soul change are two distinct artifacts; the `spec_preview` event already streams them as separate fields (`spec` + `soul_edit`, §6.3). The client echoes them back as the two separate fields `proposed_spec` + `proposed_soul_edit` on the assistant message (§6.1), so the approve path reconstructs exactly what was previewed without smuggling one inside the other and without a server-side session store. `_last_soul_edit` reads the explicit field; the spec dict is never polluted by soul data.

> **Why `edit` writes a `challenger`, not the champion.** Editing a *live* account's pipeline must not silently swap the running pipeline mid-stream. The builder stages a `challenger` (separate doc id `pipelinespecs/{aid}-challenger`, doc 04 §3b); the operator promotes it later (`promote_challenger`, doc 04 §6c — out of scope here). A brand-new account has no running pipeline, so its first spec is the `champion` directly. This honors the architecture's "validate-then-activate, default manual-promote" rule (doc 04 §6c).

> **Why re-validate on approve.** The proposal echoed by the client could be stale or tampered (the client is untrusted). Re-running the pure `validate_spec` before the only `put_document` guarantees no invalid spec is ever persisted — cheap insurance, and it reuses the exact gate. `PipelineSpecRepository.save` itself does not validate (doc 04 §6b only bumps the version), so this check is the builder's responsibility.

---

## 8. Decision Defense (non-obvious choices)

**Why stream the builder over SSE instead of a plain request/response?**
A turn does several visible-latency things — a Claude call (seconds), then validation, then mermaid compile — and the repair loop benefits from showing the assistant message *before* the validation verdict lands. SSE lets the UI render the prose reply immediately and then flip to either an error list or a diagram. It also reuses the *exact* `force_post.py` worker/queue plumbing the codebase already trusts, so there is no new concurrency surface. A non-SSE buffered fallback (§6.4) keeps it equally usable as a one-shot POST.

**Why is the conversation stateless on the server (client echoes the draft)?**
The whole rest of the posting system is request-scoped and stateless between calls (force-post recomputes everything per request; there is no session store). Introducing a `ConversationDocument` would add a persisted lifecycle (TTL, cleanup, concurrent-edit semantics) for data the client already holds. Echoing `proposed_spec`/`validation_errors` in the message history makes a turn a pure function of its request — trivially testable, no cleanup, no second source of truth. This is the simplicity-first choice CLAUDE.md asks for; the cost (a slightly larger request body) is negligible for an 8-leaf spec.

**Why does the builder only WIRE + CONFIGURE and lean entirely on `validate_spec` to enforce it?**
The "what an LLM may legally set" line is already drawn, once, in the catalog (`config_origin`, doc 03 §4.4) and enforced, once, in the validator (rejects non-`literal` config, R2; missing invariants, R7; bad terminal, R6 — doc 05 §5). Re-checking any of that in the builder would duplicate the rule and invite drift. The builder's job is narrow: render the proposable surface into the prompt so Claude *tends* to stay in bounds, then let the validator be the hard gate and route its structured errors back for repair. The prompt shapes; the validator decides. Writing tool code is impossible by construction — there is no code-writing affordance in the draft shape (`BuilderDraft` carries `spec` + `soul_edit`, never source).

**Why reuse `messages_json_dict` rather than ask for free-form text and parse it ourselves?**
`ClaudeClient._extract_json_object` (`claude_client.py:17-37`) already handles fenced ```json blocks and bare `{…}` extraction and returns `None` on failure. The builder needs exactly one JSON object per turn (`BuilderDraft`). Reusing the existing extractor means the builder inherits the same parsing the compose/guardian paths use, and a parse failure is a clean `None` we degrade gracefully on — no bespoke regex.

**Why re-validate on approve and force `account_id`/`status` server-side?**
The client is untrusted: it could echo a mutated spec, a different `account_id`, or flip `status` to `champion` to hot-swap a live pipeline. Forcing `account_id` from the request, deriving `status` from `mode`, and re-running the pure validator before the single `put_document` closes all three holes for a few microseconds of pure-function cost. The persisted spec is therefore always (a) for the right account, (b) the right status for the mode, and (c) validator-clean.

**Why edit the soul through `apply_account_update` instead of mutating `account.soul` directly?**
`apply_account_update` is the same path the dashboard PATCH uses; it normalizes `contrast_patterns`/`punctuation_rules` into their Pydantic shapes and routes through `AccountRepository.save`, which auto-bumps the voice version and archives a `VoiceRevisionDocument` (`account_repository.py:116`). Going around it would re-implement that normalization and risk an unversioned soul edit — exactly the kind of duplicated, drift-prone code to avoid. The builder edits soul fields the one supported way.

**Why render `default_pipeline_spec` as the few-shot example?**
The single hardest correctness property for any drafted spec is that its nested ids match the runbook's so `flatten_steps` yields the dotted ids `flowGraph.ts` couples to (doc 05 §6.1). Showing Claude the *actual* baseline spec (not a paraphrase) as the worked example is the cheapest, most reliable way to get drafts in the right vocabulary — and if Claude deviates, the validator's `dangling_read`/`duplicate_step_id`/`no_terminal_published` codes catch it and the repair loop fixes it. One source of truth for "what good looks like": the baseline itself.

---

## 9. Definition of Done (per slice)

**Types slice (`agent_builder_types.py`)**
- `from app.api.routes.agent_builder_types import BuilderChatRequest, BuilderChatMessage, BuilderDraft, BuilderSoulEdit` imports clean.
- `BuilderChatRequest(account_id="JohnJames_News", messages=[BuilderChatMessage(role="user", text="hi")])` validates; defaults `mode="edit"`, `approve=False`.
- `BuilderDraft.model_validate({"reply": "x"})` validates with `spec=None`, `soul_edit=None`.

**Route slice (`agent_builder.py`)**
- `python -m py_compile app/api/routes/agent_builder.py app/api/routes/agent_builder_types.py` clean.
- With a **fake Claude** injected (a `messages_json_dict` stub — the test monkeypatches `get_claude_client`), `_run_builder_turn` emits, in order:
  - draft with no spec → `[assistant_message, done]`.
  - draft with an **invalid** spec → `[assistant_message, validation_errors, done]`, and `validation_errors.errors[*].code` are the doc-05 codes (e.g. `dangling_read`).
  - draft with a **valid** spec → `[assistant_message, spec_preview, done]`, and `spec_preview.mermaid` starts with `flowchart LR` and `spec_preview.catalog_hash` equals `tool_catalog_hash()`.
  - `approve=True` with a valid `messages[-1].proposed_spec` (edit mode) → `[spec_written, done]`, `status == "challenger"`, and `PipelineSpecRepository().load(aid, "challenger")` returns the saved spec (verify against a fake repo/client).
  - `approve=True` with no proposal → `[error, done]`, `error.message` mentions "approve".
- Non-SSE POST (no `Accept: text/event-stream`) returns `{"events": [...]}` containing the same frames the SSE path would yield, terminated by `{"type":"done"}`.
- The streamed frames are valid `data: {json}\n\n` (one JSON object per frame, each with a `type`).

**Wiring slice (`main.py`)**
- `agent_builder` is imported and `include_router(...)` registered under `/api` with `dependencies=_auth` (auth-gated like every other write router, `main.py:181-186`).
- `POST /api/agent-builder/chat` is reachable (200/stream) on a running stack; an unauthenticated call is rejected by `require_auth` (same as `force_post`).

**Global**
- No file under `app/pipeline/tools/**` is created or modified (builder writes no tool code).
- `validate_spec` / `compile_spec` / `artifact_graph_mermaid` / `get_tool_catalog` / `PipelineSpecRepository` are **called, not reimplemented** (grep the diff: no second copy of validation rules, mermaid emission, or catalog introspection in `agent_builder.py`).
- The only mutating writes the builder performs are via `apply_account_create` / `apply_account_update` / `PipelineSpecRepository().save` — no direct `put_document` in `agent_builder.py`.

---

## 10. Cross-references (shared types owned elsewhere)

- **doc 03 — tool catalog:** owns the **`ToolCatalog` object** via `get_tool_catalog()` (**CC-1**: the only factory — `.get()` / `__contains__` / iterable / `run_for`, also the `catalog` argument passed to `validate_spec`/`compile_spec`), plus `get_tool()` / `tool_catalog_hash()` / `ToolCatalogDocument.proposable_params`. The builder iterates that one object to render the proposable surface into the prompt, passes the same object to the validator/compiler, and stamps the catalog hash. The `ToolCatalog`-vs-list API seam is settled by **CC-1** (one object, one factory) and pinned here in §3.2/§3.3/§3.6 — there is no separate raw-list factory in this doc.
- **doc 04 — pipeline spec + versioning:** owns `PipelineSpecDocument`/`StepSpec`/`CompositeSpec`, `default_pipeline_spec()` (the few-shot example — the **10-leaf SENSE+ACT baseline**, doc 04 §7), and `PipelineSpecRepository.save/load` (versions + archives on write; `save` mutates the spec in place and returns `None`). The builder constructs specs and writes them as `champion` (create) / `challenger` (edit). Promotion (`promote_challenger`) is out of scope.
- **doc 05 — validator + compiler:** owns the pure `validate_spec(doc, catalog) -> ValidationReport` (the gate whose `ValidationError`s stream back) and `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` (input to the mermaid renderer). The builder is a primary consumer of `ValidationReport`. `validate_spec` collects **all** errors (does not stop at the first), so `validation_errors` carries the complete repair list.
- **soul-pipeline plan (01/03):** owns `AccountSoul`, `AccountUpdateBody`/`apply_account_update`, `AccountCreateBody`/`apply_account_create`, and the auto-bump on `AccountRepository.save`. The builder edits the soul exclusively through these and never calls `bump_voice_version_if_needed` directly. All five `BuilderSoulEdit` fields (incl. `category`) map 1:1 onto `AccountUpdateBody` (§3.5).
- **doc 11 — frontend:** consumes this doc's HTTP contract. **This doc is the canonical owner of the builder-backend contract: `POST /api/agent-builder/chat`, body `BuilderChatRequest`, SSE events `assistant_message | validation_errors | spec_preview | spec_written | error | done` (§6).** Doc 11's prose was authored against a divergent assumed shape (`POST /accounts/{id}/builder/chat`, body `{message}`, events `token|proposal|complete|error`); **that divergence is resolved in favor of THIS doc** — the frontend client must be written against §6's URL/body/event union, not doc 11's placeholder. (Cross-doc: doc 11 needs a one-line update to point at this contract; flagged in StructuredOutput as it is outside this doc's edit scope.)
- **doc 14 — backend read routes (NOT this doc):** the frontend trace/graph viewer (doc 11 §3.1/§3.2) also needs the pipeline **read** routes, and per **CC-11** those are **owned by doc 14**, not here. Doc 14 owns `GET /api/accounts/{id}/pipeline/spec[?status]`, `POST /api/accounts/{id}/pipeline/spec/validate`, `GET /api/pipeline/runs/{run_id}` (the trace chain), and `GET /api/pipeline/runs/{run_id}/steps/{step_id}` (full step output) — thin reads over `PipelineSpecRepository.load_or_default` (doc 04, **CC-5**), `validate_spec` + `get_tool_catalog()` (doc 05/03, **CC-1**), and `StepOutputRepository` (doc 08). This doc deliberately does NOT add them (§2: it builds only the chat endpoint), and doc 14 is sequenced **before** doc 11 (overview §4 order: `… → 08 → 14 → 09 → 10 → 11`). No StructuredOutput flag needed — the slice is owned.
- **doc 02 — outcome ledger/attribution & doc 08 — step trace:** not on this path. The builder authors specs; attribution and trace happen when those specs *run*, which is the scheduler/interpreter's job (doc 07).

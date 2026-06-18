# Task 14 — Backend Read/Query Routes (the frontend's backend)

> **Status:** Ready to implement. Authored cold against the live tree on branch `feat/platform-overhaul`; every route, repo method, file path, and wiring line below was verified against the actual code (`pipeline_runs.py`, `main.py`, `client.ts`), not memory. This slice has zero open questions within its own scope.
> **Scope:** Backend only. ONE new route module — `app/api/routes/pipeline_spec.py` — for the two account-scoped spec reads, **one** new handler appended to the existing `app/api/routes/pipeline_runs.py` for the per-step-output read, plus the router registration in `main.py`. **No new business logic** — every handler is a thin `asyncio.to_thread` wrapper over a repo/pure function docs 04/05/03/08 already ship. No tool code, no new persistence model, no frontend.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB; in-process APScheduler).
> **DB reality:** one account today — `JohnJames_News`. RavenDB has NO multi-doc transactions and NO CAS/If-Match — irrelevant here: every route is a pure READ.

This doc OWNS the four backend read/query routes the frontend (doc 11) and the builder depend on, **per CC-11**. They are the data tap for doc 11's spec-driven flow graph, validation surface, and full-fidelity run-trace viewer:

```
GET  /api/accounts/{account_id}/pipeline/spec[?status]   → PipelineSpecRepository().load_or_default(account_id, status, kind="post")   (doc 04, CC-5)
POST /api/accounts/{account_id}/pipeline/spec/validate    → validate_spec(load_or_default(...), get_tool_catalog())                    (docs 05/03, CC-1)
GET  /api/pipeline/runs/{run_id}                          → PipelineRunDocument trace chain (run header + step_links)                   (doc 08) — REUSED, already exists
GET  /api/pipeline/runs/{run_id}/steps/{step_id}          → StepOutputRepository().get(run_id, step_id) — the FULL, untruncated step doc (doc 08)
```

**Sequence:** after 04/05/03/08 (it imports their repos/pure functions), before doc 11 (which fetches from these routes). Overview §4: `… → 08 → 14 → 09 → 10 → 11`; doc 13 §2 step 9.

---

## 1. Why this slice exists

Doc 11 (frontend) renders three things from the backend: the editable pipeline **graph** (from the loaded spec), the validator **errors** in the builder, and the full-fidelity **run-trace** chain with per-step content on click. It consumes those over HTTP via `apiFetch` (`frontend/src/api/client.ts:38-51`). The data already exists — docs 04/05/03/08 ship the repos and pure functions — but **there is no HTTP surface for three of the four reads**:

- `GET /api/pipeline/runs/{run_id}` **already exists today** (`pipeline_runs.py:45-54`, `fetchPipelineRun` at `frontend/src/api/endpoints/pipelineRuns.ts:18-20`) and already returns `PipelineRunDocument.model_dump()` — which, once doc 08 adds `step_links`, carries the trace chain for free. This doc REUSES it (no edit).
- `GET /api/accounts/{id}/pipeline/spec[?status]`, `POST /api/accounts/{id}/pipeline/spec/validate`, and `GET /api/pipeline/runs/{run_id}/steps/{step_id}` **do not exist** — they are the new work here.

Per **CC-11** this doc OWNS the contract for all four (so there is one authoritative place doc 11 mirrors), but only authors the three missing handlers; the fourth is documented REUSED so the frontend can rely on the full set landing together.

> **Load-bearing posture:** these are **thin reads**. The repos and pure functions are the single source of truth (docs 04/05/03/08). A handler that did anything other than "call the repo method `to_thread`, `.model_dump()`, return / 404" would be duplicating logic the owning docs already validated. The grep guard in §6 enforces this: no validation rule, no catalog introspection, no spec compilation lives in `pipeline_spec.py`.

---

## 2. File-by-file plan

| Kind | File | Role (one line) |
|---|---|---|
| **NEW** | `app/api/routes/pipeline_spec.py` | The two account-scoped spec reads: `GET .../pipeline/spec[?status]` (load_or_default) + `POST .../pipeline/spec/validate` (validate_spec + get_tool_catalog). Mirrors `pipeline_runs.py` exactly. |
| **CHANGED** | `app/api/routes/pipeline_runs.py` | Append ONE handler — `GET /pipeline/runs/{run_id}/steps/{step_id}` → `StepOutputRepository().get(...)`, 404 if `None`. Add a module-level `step_repo = StepOutputRepository()` beside the existing `repo`. ~10 lines; the four existing handlers are untouched. |
| **CHANGED** | `app/main.py` | Import `pipeline_spec` (add to the line-13 route import) and `app.include_router(pipeline_spec.router, prefix="/api", tags=["pipeline-spec"], dependencies=_auth)` (mirrors `main.py:184`). One import edit + one `include_router` line. |
| **NEW** | `tests/unit/test_pipeline_spec_routes.py` | `TestClient` route tests for the three new behaviors (mirror of `tests/unit/test_force_post_routes.py`): spec read returns the baseline (never 404s), validate returns `{ok, errors}`, step-output 404s on unknown / returns the full doc on known. |
| **REUSED (verbatim, unchanged)** | `app/api/routes/pipeline_runs.py:45-54` | `GET /pipeline/runs/{run_id}` already returns `PipelineRunDocument.model_dump()` (the trace chain once doc 08 adds `step_links`). This doc does NOT re-implement it. |
| **REUSED** | `app/services/pipeline_spec_repository.py` (doc 04) | `PipelineSpecRepository().load_or_default(account_id, status, kind="post")` — CC-5, the single loader; returns the version-stamped baseline when no doc exists (never `None`). |
| **REUSED** | `app/pipeline/spec/validator.py` + `app/pipeline/spec/catalog.py` (docs 05/03) | `validate_spec(doc, catalog) -> ValidationReport` (doc 05 §5.2) + `get_tool_catalog() -> ToolCatalog` (doc 03, CC-1: the single factory). |
| **REUSED** | `app/services/step_output_repository.py` (doc 08) | `StepOutputRepository().get(run_id, step_id) -> StepOutputDocument | None` (doc 08 §5). |
| **REUSED (pattern)** | `app/api/routes/pipeline_runs.py:21-54` | `router = APIRouter()`, module-level repo, `await asyncio.to_thread(repo.method, …)`, `.model_dump()`, `HTTPException(status_code=404, …)`. Copied, not imported. |
| **REUSED (pattern)** | `app/api/routes/accounts.py` path-param style | `GET /accounts/{account_id}/…` path shape for the account-scoped spec routes. |

**Implementation order:** `pipeline_spec.py` → append to `pipeline_runs.py` → wire `main.py` → tests. Each compiles on its own once its prerequisite docs (04/05/03/08) are on disk.

---

## 3. Shared-type contracts this slice depends on (owned elsewhere)

These are the **exact** members the handlers call. If an owning doc renames one, the change is localized to the one helper line here.

### 3.1 `PipelineSpecRepository.load_or_default` — **doc 04** (`app/services/pipeline_spec_repository.py`)

```python
# doc 04 §6b — the single loader entry point (CC-5). Returns the CHAMPION (or seeded
# baseline) for this kind; the in-memory baseline is version-STAMPED so version_hash is
# never None. Signature verified against doc 04 §6b.
def load_or_default(self, account_id: str, status: str = "champion", kind: str = "post") -> PipelineSpecDocument: ...
```

Used here: `PipelineSpecRepository().load_or_default(account_id, status, "post")` → `.model_dump()`. **It never returns `None`** (CC-5: no doc → baseline), so `GET .../pipeline/spec` **never 404s** — the graph always renders (doc 11 §3.1 relies on this). `status` is a `Literal["champion", "challenger"]` query param defaulting to `"champion"` (doc 04 §3b §130). `kind` is **always `"post"`** here (the reply family is doc 12, out of scope — CC-12).

### 3.2 `validate_spec` + `get_tool_catalog` — **docs 05 / 03**

```python
# doc 05 §5.2 — pure, no I/O. Returns a Pydantic ValidationReport{ok: bool, errors: list[ValidationError]}.
def validate_spec(doc: PipelineSpecDocument, catalog: ToolCatalog) -> ValidationReport: ...

# doc 03 / CC-1 — the ONLY catalog factory; returns the ToolCatalog OBJECT (not a raw list).
def get_tool_catalog() -> ToolCatalog: ...
```

Used here: `validate_spec(load_or_default(account_id, status, "post"), get_tool_catalog()).model_dump()`. **`catalog` is the `ToolCatalog` object from `get_tool_catalog()`** — the same object every other caller passes (validator/compiler doc 05, promotion doc 04 §6c, builder doc 10). Per **CC-1** the name `build_catalog()` does not exist and the arg is never a raw `list[ToolCatalogDocument]`; there is no cross-doc disagreement to resolve. `ValidationReport.model_dump()` yields `{"ok": bool, "errors": [{code, step_id, artifact, detail}]}` (doc 05 §5.2) — exactly what doc 11 §2.2 mirrors.

### 3.3 `StepOutputRepository.get` — **doc 08** (`app/services/step_output_repository.py`)

```python
# doc 08 §5. Rebuilds the doc id stepoutputs/{run_id}/{step_id} internally; returns the
# FULL untruncated StepOutputDocument or None. Verified against doc 08 §5.
def get(self, run_id: str, step_id: str) -> StepOutputDocument | None: ...
```

Used here: `StepOutputRepository().get(run_id, step_id)` → `.model_dump()`, **404 if `None`**. The dotted `step_id` (e.g. `summarize_for_compose.analyze_external_references.rank_external_references`) **contains no slash**, so a single FastAPI path segment is safe — `get()` rebuilds the slash-bearing doc id (`stepoutputs/{run_id}/{step_id}`) from the two clean params, and the slash is never exposed in the URL (doc 08 §5; doc 11 §3.2). `StepOutputDocument.model_dump()` carries the full untruncated `inputs`/`outputs`/`result_payload` (doc 08 §4) — **no truncation**, which is the explicit user requirement.

### 3.4 `PipelineRunDocument` (the trace chain) — **doc 08** (REUSED route)

`GET /pipeline/runs/{run_id}` (`pipeline_runs.py:45-54`) already returns `run.model_dump()`. Once doc 08 adds `step_links: list[StepLink]` to `PipelineRunDocument` (doc 08 §4), that same dump carries the ordered trace chain (`step_links[].{step_id, scope, seq, status, duration_ms, doc_id}`). **No edit to this handler** — the field rides through `.model_dump()` automatically. The viewer (doc 11 §5) follows `step_links` and fetches each step's full content via §3.3's route.

---

## 4. The routes (exact request/response shapes)

### 4.1 `GET /api/accounts/{account_id}/pipeline/spec` — load the live spec

```
GET /api/accounts/JohnJames_News/pipeline/spec
GET /api/accounts/JohnJames_News/pipeline/spec?status=challenger
→ 200  application/json
   PipelineSpecDocument.model_dump()  — { account_id, steps[], status, parent_hash,
                                          version_hash, version_seq, version_label }
   (never 404 — load_or_default returns the version-stamped baseline when no doc exists)
```

`status` ∈ `{champion, challenger}` (default `champion`). `kind` is fixed `"post"` (not exposed).

### 4.2 `POST /api/accounts/{account_id}/pipeline/spec/validate` — validate the live spec

```
POST /api/accounts/JohnJames_News/pipeline/spec/validate
POST /api/accounts/JohnJames_News/pipeline/spec/validate?status=challenger
(no request body — validates the SERVER's loaded spec, not a client-supplied one)
→ 200  application/json
   ValidationReport.model_dump()  — { ok: bool, errors: [{ code, step_id, artifact, detail }] }
```

> **Decision Defense — validate the SERVER-LOADED spec, not a body the client POSTs.** Doc 11 §3.1's `validateAccountSpec(accountId)` posts **no body** — it asks "is the spec currently persisted for this account valid?" That is a read-then-check over `load_or_default`, the same spec the graph renders. Validating a client-supplied draft is the **builder's** job and rides doc 10's `POST /api/agent-builder/chat` (which has the catalog + Claude loop + `approve` write). Accepting a spec body here would create a **second, unowned write-adjacent validation surface** that drifts from doc 10's — exactly the duplication CLAUDE.md §3 forbids. So this route is `POST` only for verb-correctness (it is an action, not a cacheable GET) and is otherwise a pure read: it loads the account's own spec and runs the pure validator. (Doc 13 §0.1 pins this exact body-less shape: `validate_spec(load_or_default(account_id, status), get_tool_catalog()).model_dump()`.)

### 4.3 `GET /api/pipeline/runs/{run_id}` — the trace chain (REUSED, already exists)

```
GET /api/pipeline/runs/{run_id}
→ 200  PipelineRunDocument.model_dump()  — run header + step_links[] (doc 08) + legacy steps[]
→ 404  { detail: "Run not found" }   (when neither the projection nor a JetStream replay yields a run)
```

Unchanged from `pipeline_runs.py:45-54`. After doc 08 lands, the dump includes `step_links` for free. (Note: the existing handler also folds the run live from JetStream on a projection miss — irrelevant to the trace, which reads `step_links` written by doc 08's in-process sink independent of NATS; on a real run the persisted header is present.)

### 4.4 `GET /api/pipeline/runs/{run_id}/steps/{step_id}` — one step's FULL content

```
GET /api/pipeline/runs/{run_id}/steps/load_account_bundle
GET /api/pipeline/runs/{run_id}/steps/summarize_for_compose.analyze_own_posts.rank_own_posts
→ 200  StepOutputDocument.model_dump()  — { run_id, account_id, step_id, scope, seq, status,
                                            inputs[], outputs[], result_payload, ... } — UNTRUNCATED
→ 404  { detail: "Step output not found" }   (when StepOutputRepository.get(...) is None)
```

---

## 5. The implementation

### 5.1 `app/api/routes/pipeline_spec.py` (NEW)

Mirrors `pipeline_runs.py` line-for-line: module-level `router` + `repo`, `await asyncio.to_thread(...)` over the blocking RavenDB load, `.model_dump()` return. The catalog factory is called per-request (cheap pure assembly per doc 03; matches how `pipeline_runs.py` constructs nothing per request beyond the `to_thread` call).

```python
"""Read API for the per-account pipeline spec (doc 14, CC-11).

Two thin reads the frontend graph + builder consume (doc 11 §3.1):
  GET  /accounts/{id}/pipeline/spec[?status]   → the loaded champion/challenger spec
  POST /accounts/{id}/pipeline/spec/validate   → validate_spec over that loaded spec

No business logic lives here — both handlers wrap repo/pure functions docs 04/05/03 ship.
Mirrors pipeline_runs.py exactly (router + module-level repo + asyncio.to_thread).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Query

from app.pipeline.spec.catalog import get_tool_catalog          # doc 03 (CC-1: the only factory)
from app.pipeline.spec.validator import validate_spec           # doc 05 §5.2 (pure)
from app.services.pipeline_spec_repository import PipelineSpecRepository  # doc 04 §6b (CC-5)

router = APIRouter()
repo = PipelineSpecRepository()

SpecStatus = Literal["champion", "challenger"]


@router.get("/accounts/{account_id}/pipeline/spec")
async def get_account_spec(
    account_id: str, status: SpecStatus = Query("champion")
) -> dict[str, Any]:
    # load_or_default never returns None (CC-5: no doc → version-stamped baseline),
    # so this never 404s — the graph always renders (doc 11 §3.1).
    spec = await asyncio.to_thread(repo.load_or_default, account_id, status, "post")
    return spec.model_dump()


@router.post("/accounts/{account_id}/pipeline/spec/validate")
async def validate_account_spec(
    account_id: str, status: SpecStatus = Query("champion")
) -> dict[str, Any]:
    # Validate the SERVER's loaded spec (no client body — see §4.2 Decision Defense).
    spec = await asyncio.to_thread(repo.load_or_default, account_id, status, "post")
    report = validate_spec(spec, get_tool_catalog())   # CC-1 catalog object; pure, no to_thread needed
    return report.model_dump()
```

> `validate_spec` + `get_tool_catalog` are **pure, in-memory** (doc 05 §1; doc 03 builds the catalog by introspection with no I/O), so they run inline — only the RavenDB `load_or_default` goes through `asyncio.to_thread` (matching `pipeline_runs.py:31,41,47`, which `to_thread`s only the RavenDB call). If a future catalog build does I/O, wrap the two-line `validate` body in one `to_thread` — single localized change.

### 5.2 `app/api/routes/pipeline_runs.py` (CHANGED — append one handler)

The step-output read belongs in the module that owns `/pipeline/runs/*`. Add a second module-level repo and one handler; the four existing handlers (`:25-71`) are untouched.

```python
# add to the imports block:
from app.services.step_output_repository import StepOutputRepository   # doc 08 §5

# add beside `repo = PipelineRunRepository()` (line 22):
step_repo = StepOutputRepository()

# append after get_run (after line 54), BEFORE get_run_events / stream_run so the more
# specific /steps/{step_id} path is registered (FastAPI matches by registration order;
# /steps/{step_id} and /events/{...} do not overlap, but keep the run-detail group together):
@router.get("/pipeline/runs/{run_id}/steps/{step_id}")
async def get_step_output(run_id: str, step_id: str) -> dict[str, Any]:
    """The FULL, untruncated StepOutputDocument for one step (doc 08 §4). 404 if absent.
    The dotted step_id carries no slash, so a single path segment is safe (doc 08 §5)."""
    doc = await asyncio.to_thread(step_repo.get, run_id, step_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Step output not found")
    return doc.model_dump()
```

> `HTTPException`, `asyncio`, `Any`, and `APIRouter` are already imported in `pipeline_runs.py` (`:10-15`) — no new imports beyond `StepOutputRepository`. `step_repo` is module-level so the test can `monkeypatch.setattr(pipeline_runs, "step_repo", mock)` exactly as `test_force_post_routes.py:20` patches `repo`.

> **Decision Defense — append the step-output route to `pipeline_runs.py`, not a new file.** It is keyed on `/pipeline/runs/{run_id}/…` — the same namespace `pipeline_runs.py` already owns (run list, run detail, events, stream). The two new *account-scoped spec* routes (`/accounts/{id}/pipeline/spec…`) are a genuinely different resource family, so they earn their own module (matching doc 13 §0.1's `pipeline_spec.py` name). Splitting the step-output route into yet another module would scatter the `/pipeline/runs/*` surface across two files for one handler — the opposite of surgical.

### 5.3 `app/main.py` (CHANGED — register the new router)

`pipeline_runs.router` is already registered (`main.py:184`), so the appended step-output handler is live with no main.py edit. Only the **new** `pipeline_spec` module needs wiring:

```python
# line 13 — add pipeline_spec to the route import:
from app.api.routes import (
    accounts, analytics, oauth, posts, dashboard, health, force_post,
    pipeline_runs, pipeline_spec, auth,
)

# after main.py:184 (the pipeline_runs include) — add, auth-gated like every read router:
app.include_router(pipeline_spec.router, prefix="/api", tags=["pipeline-spec"], dependencies=_auth)
```

`dependencies=_auth` (`= [Depends(require_auth)]`, `main.py:180`) gates these reads behind the dashboard login exactly like `accounts`/`pipeline_runs` — verified the pattern at `main.py:181-186`.

---

## 6. Definition of Done (per slice)

**Slice 1 — `pipeline_spec.py`**
- `python -m py_compile app/api/routes/pipeline_spec.py` clean.
- `GET /api/accounts/JohnJames_News/pipeline/spec` → 200; body is a `PipelineSpecDocument` dump with the **10 dotted leaf ids** when flattened (doc 04 §8 baseline) and a non-`None` `version_hash` (the in-memory stamp, doc 04 §6b). **Never 404s** even before `pipelinespecs/JohnJames_News` is seeded.
- `GET …/pipeline/spec?status=challenger` → 200 with the challenger when one exists, else the baseline (CC-5).
- `POST /api/accounts/JohnJames_News/pipeline/spec/validate` → 200; body is `{ok: bool, errors: [...]}`. On the seeded baseline (after doc 06 lands the ACT artifacts/tools — doc 04 §7 sequencing note) `ok is True`. Error entries are the doc-05 code shape `{code, step_id, artifact, detail}`.

**Slice 2 — `pipeline_runs.py` step-output handler**
- `python -m py_compile app/api/routes/pipeline_runs.py` clean; the four existing handlers unchanged.
- `GET /api/pipeline/runs/{run_id}/steps/{step_id}` → 200 with the **full untruncated** `StepOutputDocument` dump when present; a `timeline_references` output `value` > 8000 chars is returned **whole** (no `… [truncated]` marker — doc 08 §4 stores it whole).
- The same route on an unknown `(run_id, step_id)` → **404** `{detail: "Step output not found"}`.
- A dotted `step_id` (`summarize_for_compose.analyze_own_posts.rank_own_posts`) resolves in a single path segment (no slash in the URL).

**Slice 3 — `main.py` wiring**
- `pipeline_spec` imported (line 13) and `include_router(...)` registered under `/api` with `dependencies=_auth` (mirrors `main.py:184`).
- All four routes reachable on a running stack; an **unauthenticated** call to any of them is rejected by `require_auth` (same gate as `force_post`/`pipeline_runs`).
- `GET /api/pipeline/runs/{run_id}` (REUSED, `pipeline_runs.py:45`) returns `step_links` in its dump after doc 08 lands — **no edit made** to that handler.

**Slice 4 — `tests/unit/test_pipeline_spec_routes.py`** (mirror of `test_force_post_routes.py`)
- `TestClient(app)`; `monkeypatch.setattr(pipeline_spec, "repo", fake)` / `monkeypatch.setattr(pipeline_runs, "step_repo", fake)` injects fakes (no RavenDB).
- `get_account_spec`: fake `load_or_default` returns a `PipelineSpecDocument` → 200, body `account_id` matches, body `status` defaults to `champion`; `?status=challenger` passes `status="challenger"` to the repo.
- `validate_account_spec`: monkeypatch `validate_spec` (or use a real baseline + real catalog) → 200, body has `ok` and `errors` keys; a crafted invalid spec yields `ok=False` with doc-05 codes.
- `get_step_output`: fake `step_repo.get` returns `None` → 404; returns a `StepOutputDocument` → 200 with full `inputs`/`outputs`.

**Global**
- `python -m py_compile app/api/routes/pipeline_spec.py app/api/routes/pipeline_runs.py app/main.py` clean.
- `cd SocialMediaAutonomousAgents/backend && python -m pytest -q tests/unit/test_pipeline_spec_routes.py` → green.
- **Grep guard (thin-reads invariant — should return nothing):** no validation/catalog/compile logic re-implemented in the route module:
  ```bash
  cd SocialMediaAutonomousAgents/backend
  grep -nE "for .* in .*\.steps|ArtifactKey|compile_spec|build_catalog|put_document" app/api/routes/pipeline_spec.py   # must be EMPTY
  ```
  (The handlers only call `repo.load_or_default`, `validate_spec`, `get_tool_catalog`, `step_repo.get`, and `.model_dump()` — no second copy of any rule.)
- Doc 11's clients (`api/endpoints/pipelineSpec.ts` `fetchAccountSpec`/`validateAccountSpec`, `api/endpoints/stepOutputs.ts` `fetchStepOutput`, and the existing `fetchPipelineRun`) resolve against these exact paths — **doc 11 owns the TS clients; this doc owns the routes they hit.** The contracts match doc 11 §3.1/§3.2 verbatim (verified: path templates, query param, JSON shapes).

---

## 7. Cross-references (what this doc owns vs. assumes)

- **Owns (per CC-11):** the four read-route **contracts** — `GET /api/accounts/{id}/pipeline/spec[?status]`, `POST /api/accounts/{id}/pipeline/spec/validate`, `GET /api/pipeline/runs/{run_id}` (REUSED), `GET /api/pipeline/runs/{run_id}/steps/{step_id}` — and the three new handlers + their wiring. Doc 11 §3.1/§3.2 mirrors these read-only and flags this doc as owner; doc 10 §553 and doc 13 §0.1 both defer the read-route slice here.
- **doc 04** — owns `PipelineSpecRepository.load_or_default` (CC-5, the single loader; never `None`) and `PipelineSpecDocument`. This doc calls `load_or_default`, never constructs or saves a spec.
- **doc 05 / doc 03** — own `validate_spec(doc, catalog) -> ValidationReport` and `get_tool_catalog() -> ToolCatalog` (CC-1, the single factory; no `build_catalog()`). This doc passes the `ToolCatalog` object straight in — the same object every caller uses; no list-vs-object seam to reconcile.
- **doc 08** — owns `StepOutputRepository.get`, `StepOutputDocument`, and the `step_links` field on `PipelineRunDocument`. This doc returns those dumps untouched; `step_links` rides through the REUSED run-detail route automatically.
- **doc 10** — owns the **builder** write path (`POST /api/agent-builder/chat` with `approve`). This doc's `/validate` route is read-only and validates the **server-loaded** spec, never a client draft — no overlap with doc 10's validate-then-write flow (§4.2).
- **doc 11** — owns the frontend TS clients (`pipelineSpec.ts`, `stepOutputs.ts`) and the run-trace viewer. It consumes these routes; it does not register them.
- **doc 12 (replies)** — `kind="reply"` is a separate family (CC-12); this doc hard-codes `kind="post"` and does NOT expose `kind`. If replies ship, a `?kind=` param is an additive, separate change (out of scope).

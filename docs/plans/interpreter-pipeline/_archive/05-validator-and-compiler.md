# Task 05 — Validator (pure) + Compiler

> **Status:** Ready to implement. Authored against the canonical sibling docs (03 catalog, 04 spec model, 06 ACT tail) and the verified live code on `feat/platform-overhaul`. Reconciled with the dry-run; this slice has zero open questions.
> **Scope:** Backend only — two new pure modules under `app/pipeline/spec/`: `validator.py` (static checks on a `PipelineSpecDocument` against the tool catalog) and `compiler.py` (`PipelineSpecDocument` → `tuple[Step, ...]` via the existing `chain()`/`parallel()` helpers).
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB).
> **Architecture:** THE INTERPRETER. This task is the gate the builder calls before it activates a spec, plus the lowering step that turns spec data into the typed `Step` tree the existing engine already runs.
>
> **What this slice does NOT do:** it does not execute anything, does not touch RavenDB, does not inject the cost/safety wrappers (that is the engine's job — see §4 and **doc 07**), and does not define the catalog or the spec document (the catalog is **doc 03**, the spec document is **doc 04**). It is two pure functions: `validate_spec(doc, catalog) -> ValidationReport` and `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]`. The `catalog` they accept is the **`ToolCatalog` object** (CC-1) — doc 03's lookup wrapper exposing `.get(tool_id)` / `tool_id in catalog` / `run_for(tool_id)` — produced by the **single factory `get_tool_catalog()`**; `compile_spec` defaults `catalog=None` and falls back to `get_tool_catalog()` internally.

---

## 1. Why this task

The interpreter makes each account's pipeline editable **data** (`PipelineSpecDocument`, doc 04) executed by one generic in-process interpreter (doc 07). Between "the builder produced/edited a spec" and "the engine runs it" there must be a **static gate** that refuses an incoherent spec *before* it is ever activated or run, and a **lowering function** that produces the exact `Step` tree the existing engine consumes.

Two pure functions, separated on purpose:

| Function | Module | Job | Pure? |
|---|---|---|---|
| `validate_spec(doc, catalog)` | `spec/validator.py` | Refuse dangling reads, cycles, missing terminal, bad config types, unknown tools, and missing/bypassed invariants. Returns a structured `ValidationReport`. | Yes — no I/O, no engine, no RavenDB. |
| `compile_spec(doc, *, catalog=None)` | `spec/compiler.py` | Lower a (validated) spec into `tuple[Step, ...]` using `chain()`/`parallel()`, **reproducing the exact `flatten_steps` dotted-id scheme** so frontend node ids still match. | Yes — no I/O. |

Keeping these pure is the whole point: the builder (doc 10) and the self-rewrite loop (doc 09) call `validate_spec` as a cheap, deterministic check; the interpreter (doc 07) and `promote_challenger` (doc 04 §6c) call `compile_spec`. Neither pulls in services.

**The load-bearing constraint for the compiler:** the frontend flow diagram (`frontend/src/lib/pipeline/flowGraph.ts`) hard-codes dotted step ids like `summarize_for_compose.analyze_external_references.rank_external_references` and matches them against `flatten_steps()` output (the runbook file warns about this at `app/pipeline/runbooks/post_tick.py:6-11`). If `compile_spec()` produces a `Step` tree whose `flatten_steps()` ids differ from the hand-written `POST_TICK_REFERENCE_STEPS`, the dashboard nodes go dark. So the compiler is graded against an exact-string round-trip, not "looks right".

---

## 2. Files

### NEW

| File | Role (one line) |
|---|---|
| `app/pipeline/spec/__init__.py` | Package marker, **created by doc 03** (the catalog package). This slice only *adds* the re-export lines `validate_spec`, `ValidationReport`, `ValidationError`, `compile_spec` to the existing file — it does not recreate it. (Sequencing: doc 03 lands first, per doc 13; if this slice runs before doc 03, create the one-line package marker, and doc 03's later edit is additive.) |
| `app/pipeline/spec/internal_primitives.py` | `INTERNAL_PRIMITIVES: dict[str, dict]` + `is_internal()` — the closed `_internal.*` table (CC-8) both `validator.py` and `compiler.py` consult. Today one entry: `"_internal.collect_external"` → `{run: steps.collect_external_references, reads: (SEARCH_REFERENCES,), writes: (TIMELINE_REFERENCES,)}`. Doc 04 §7 names this module as owned **here**. |
| `app/pipeline/spec/validator.py` | Pure `validate_spec(doc, catalog) -> ValidationReport` + the report/error-code models. |
| `app/pipeline/spec/compiler.py` | Pure `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` building the `Step` tree via `chain`/`parallel`. |
| `tests/unit/pipeline/test_spec_validator.py` | One test per error code + a happy-path on the baseline-plus-ACT-tail spec. |
| `tests/unit/pipeline/test_spec_compiler.py` | The dotted-id round-trip lock against `POST_TICK_REFERENCE_STEPS` (the regression the runbook comment asks for). |

### REUSED (verified, unchanged)

| File:line | What this slice uses it for |
|---|---|
| `app/pipeline/types/flow.py:18-33` | `Step` dataclass (`id, run, reads, writes, reads_optional, purpose, children, composite_kind`) — the compile target. |
| `app/pipeline/types/flow.py:48-66` | `parallel(*steps, id, purpose="") -> Step` — composite builder the compiler calls. |
| `app/pipeline/types/flow.py:69-91` | `chain(*steps, id, purpose="") -> Step` — composite builder the compiler calls. |
| `app/pipeline/types/flow.py:103-124` | `flatten_steps(steps, *, parent_id=None) -> list[FlatStep]` — the dotted-id scheme the compiler must reproduce (used only in tests here; the engine `run_steps` calls it at run time — see doc 07). |
| `app/pipeline/types/artifacts.py:16-24` | `ArtifactKey(StrEnum)` — the validator resolves spec read/write `.value` strings to these; the compiler lifts the spec node's read/write strings back to `ArtifactKey` members for each `Step`. |
| `app/pipeline/types/artifacts.py:119-176` | `ArtifactDef` + `ARTIFACTS` — the registry of valid artifact keys (8 SENSE keys today; **doc 06** adds the 3 ACT-tail keys `COMPOSED_POST`/`SAFETY_VERDICT`/`PUBLISHED_POST`, see §3). |
| `app/pipeline/types/tool.py:9-15` | `StepResult` — the return type of the `services/steps.py` wrappers the compiler binds as `Step.run`; this slice does not construct it. |

### Defined by sibling docs (referenced, NOT authored here)

| Symbol | Owning doc | What this slice assumes about it (see §3 for the exact contract) |
|---|---|---|
| `PipelineSpecDocument` (+ `StepSpec`, `CompositeSpec`) | **doc 04** | The input `doc`. The canonical model is `StepSpec {kind:"step", id, tool_id, reads, writes, reads_optional, config, purpose}` + a separate recursive `CompositeSpec {kind:"parallel"\|"chain", id, children, purpose}`. Field names/shape this slice depends on are pinned in §3.1. |
| `ToolCatalogDocument` (+ `ToolParameter`) and the `ToolCatalog` lookup class + factory `get_tool_catalog()` | **doc 03** | The `catalog` arg is the **`ToolCatalog` object** doc 03 produces (CC-1: `.get(tool_id) -> ToolCatalogDocument \| None`, `tool_id in catalog`, iterable, `run_for(tool_id)`). `get_tool_catalog()` is the **only** factory — the name `build_catalog()` is removed everywhere (CC-1). The catalog entry fields this slice reads are pinned in §3.2. |
| ACT-tail artifact keys `COMPOSED_POST`, `SAFETY_VERDICT`, `PUBLISHED_POST` | **doc 06** (added to `ArtifactKey`/`ARTIFACTS`) | The terminal-write check (§5, R6) and the `compose_until_safe` tool's declared writes. `PublishedPost`/`SafetyVerdict` model shapes are canonical from doc 06 §3.2. |
| ACT-tail catalog tools `llm.compose_until_safe`, `data.publish_post` | **doc 06** (added to `_TOOL_MODULES`, so they appear in `get_tool_catalog()`) | The invariant detection (§5, R7) by **artifact writes** (CC-2). Their declared `writes`/`reads` are pinned in §3.2. |
| The cost/safety wrapper injection in `run_steps` | **doc 07** | NOT in the spec or the compiler output. The validator only asserts the *invariant artifacts are written* (CC-2: detection by artifact writes, no flag — §5, R7). |

> **Sequencing (per doc 13, §0 dependency table).** Doc 03 (catalog) and doc 04 (spec model) land **before** this slice; doc 06 (ACT-tail tools + artifact keys) lands **after**. This means the *engine-runnable* baseline that passes `validate_spec` (one with `compose_until_safe`+`publish_post` and the 3 ACT artifact keys) only exists once doc 06 has merged. **This slice's tests therefore use a self-contained fixture catalog + fixture spec (§8) that mirror doc 06's declared tools, so the validator/compiler can be implemented and unit-tested without doc 06 on disk.** The doc-04 *seed* spec (8 SENSE leaves only) is intentionally NOT validatable by R6/R7 until doc 06 appends the ACT tail to the seed — doc 04 §7 / doc 06 §7.1 own that append; see the §5 R6/R7 note.

---

## 3. Shared-type contracts this slice depends on

These are the **exact** fields the validator/compiler read, copied from the canonical owner docs (04 for the spec node, 03 for the catalog). The §3.3 accessor helpers are the single adapter point if a later edit renames a field.

> **The two settled cross-doc reconciliations this section locks (resolved here, not deferred):**
> 1. **Spec node model = doc 04's** (`StepSpec` leaf with `kind="step"` + separate `CompositeSpec` for composites). Doc 05 is the only doc that had drifted to a unified `SpecStep {kind:"leaf"}`; that is corrected below to match the owner.
> 2. **Catalog = doc 03's `ToolCatalog` object (CC-1).** `validate_spec(doc, catalog)` and `compile_spec(doc, *, catalog=...)` accept the **`ToolCatalog` lookup object** doc 03 ships — exposing `.get(tool_id) -> ToolCatalogDocument | None`, `tool_id in catalog`, iteration over its `ToolCatalogDocument`s, and `run_for(tool_id) -> Callable | None`. The **only** factory is `get_tool_catalog()` (the name `build_catalog()` is removed everywhere — CC-1); this is exactly what doc 09 §5.1 passes and doc 10 §3.6 defaults to. Doc 05 reads catalog-entry fields off the `ToolCatalogDocument` that `.get()` returns; it does **not** invent a separate `ToolDef`/`config_schema`/`invariant_tool` class. Per-tool `reads`/`writes` and proposable config come from the **spec node** (doc 04 stores `reads`/`writes`/`config` on `StepSpec`) and the catalog entry's `proposable_params`/`config_origin` (doc 03), never from a non-existent `tool.reads`. **Invariant detection is by ARTIFACT writes only (CC-2)** — doc 05 never reads doc 03's `invariant_tool` flag; R7 keys off the catalog entry's declared `writes` (which artifact the tool produces), so the validator stays flag-free.

### 3.1 `PipelineSpecDocument` (doc 04) — the input

This is doc 04 §3b's canonical model, **verbatim**. Do not paraphrase it into a different shape.

```python
# app/models/pipeline_spec.py — OWNED BY DOC 04. Reproduced read-only.
class StepSpec(BaseModel):
    kind: Literal["step"] = "step"            # leaf discriminant is the STRING "step"
    id: str                                   # e.g. "rank_external_references"
    tool_id: str                              # catalog id, e.g. "deterministic.reference_rank"
    reads: list[str] = []                     # ArtifactKey .value strings (authored fact)
    writes: list[str] = []                    # ArtifactKey .value strings (authored fact)
    reads_optional: list[str] = []
    config: dict = {}                         # proposable config ONLY (builder-tunable)
    purpose: str = ""

class CompositeSpec(BaseModel):
    kind: Literal["parallel", "chain"]        # composite discriminant
    id: str
    children: list["StepSpec | CompositeSpec"] = []   # nests; mirrors flow.parallel/chain
    purpose: str = ""
    # NOTE: composites carry NO reads/writes — flow.parallel()/chain() derive them
    # by union at compile time (doc 04 §3b Decision Defense). Do not read them here.

class PipelineSpecDocument(BaseModel):
    account_id: str
    steps: list[StepSpec | CompositeSpec]     # top-level ordered steps (leaves or composites)
    status: Literal["champion", "challenger"] = "champion"
    version_hash: str | None = None
    # ... version_seq / version_label / parent_hash — bookkeeping irrelevant to this slice
```

Read-only contract used here, per node:
- **leaf** (`StepSpec`): `node.kind == "step"`, `node.id`, `node.tool_id`, `node.reads`, `node.writes`, `node.reads_optional`, `node.config`, `node.purpose`.
- **composite** (`CompositeSpec`): `node.kind in ("parallel","chain")`, `node.id`, `node.children`, `node.purpose`.

Two consequences the validator/compiler must respect (both flow from doc 04 owning the model):
- The leaf discriminant value is the literal string **`"step"`**, NOT `"leaf"`. The accessor `_step_kind` (§3.3) maps `"step"` → internal `"leaf"` so the rest of this module reads naturally.
- **`reads`/`writes` are authored on the leaf `StepSpec` node** (doc 04 §3b stores them; the seed copies them from the runbook `Step.reads`/`writes`). The validator's R3/R4 read them from `node.reads`/`node.writes`, NOT from the catalog (the catalog has no `reads` field — see §3.2). The compiler likewise lowers leaf `reads`/`writes` from the spec node. This is the single, consistent answer to "where do reads/writes come from": **the spec node**, validated for *existence-as-ArtifactKey* against the `ArtifactKey` enum and for *coherence* against upstream writes.

### 3.2 The tool catalog (doc 03) — the reference

Doc 03 is the catalog owner and ships a `ToolCatalog` **lookup object** (CC-1) over a list of `ToolCatalogDocument`s, built by the single factory `get_tool_catalog()`. This slice consumes that object directly:

```python
# app/pipeline/spec/catalog.py + app/models/tool_catalog.py — OWNED BY DOC 03.
def get_tool_catalog() -> ToolCatalog: ...   # the ONLY factory (CC-1); build_catalog() is removed

class ToolCatalog:                            # the lookup OBJECT docs 05/09/10 consume
    def get(self, tool_id: str) -> ToolCatalogDocument | None: ...
    def __contains__(self, tool_id: str) -> bool: ...
    def __iter__(self): ...                   # iterates the ToolCatalogDocuments (stable order)
    def run_for(self, tool_id: str) -> Callable | None: ...   # bound (ctx, deps) wrapper, or None when shared

class ToolParameter(BaseModel):
    name: str
    annotation: str = ""
    required: bool = False
    default: Any = None
    kind: Literal["injected", "config"]
    config_origin: Literal["injected", "runtime", "wired", "literal"]   # only "literal" is proposable

class ToolCatalogDocument(BaseModel):
    tool_id: str
    kind: str = ""                     # data | deterministic | llm
    purpose: str = ""
    source: str | None = None
    prompt_stem: str | None = None
    output_model: str | None = None
    reads: list[str] | None = None     # fixed reads (ACT tools via TOOL_READS), or None when dynamic
    writes: list[str] | None = None    # artifact ctx-keys, or None when dynamic (store_key)
    parameters: list[ToolParameter] = []
    @property
    def proposable_params(self) -> list[ToolParameter]: ...   # config_origin == "literal"
```

**The `catalog` argument is the `ToolCatalog` object (CC-1).** `validate_spec(doc, catalog)` and `compile_spec(doc, *, catalog=...)` use `catalog.get(tool_id)` / `tool_id in catalog` directly — no internal `{d.tool_id: d}` index, because the object already is one (`_tool(catalog, tool_id)` in §3.3 is now a one-line `catalog.get(tool_id)` adapter). This is exactly what doc 09 §5.1 passes (`catalog = get_tool_catalog(); validate_spec(proposal, catalog)`) and what doc 10 §3.6's `_load_catalog()` returns. **The single factory is `get_tool_catalog()`; `build_catalog()` is removed everywhere (CC-1).**

**What the catalog does and does NOT provide (and where the missing pieces come from):**
- **`writes`** — present, but `None` for the two dynamic-`store_key` rankers/briefs (doc 03 §3). The validator/compiler therefore do **not** rely on `catalog.get(id).writes` for the dataflow graph; they use the **spec node's** `writes` (doc 04 stores the concrete resolved key per step). The catalog `writes` is used only as a *cross-check* in R7's invariant detection where it is unambiguous (the ACT tools `publish_post`/`compose_until_safe` declare static `TOOL_WRITES`, so their `ToolCatalogDocument.writes` is concrete — verified doc 06 §5: `publish_post` `TOOL_WRITES=(PUBLISHED_POST,)`, `compose_until_safe` `TOOL_WRITES=(COMPOSED_POST, SAFETY_VERDICT)`).
- **`reads`** — present only for the ACT tools (doc 03 §4.3b derives it from a `TOOL_READS` constant the doc-06 ACT tools declare); `None` for the six SENSE tools (no `TOOL_READS`, dynamic per `store_key`). The dataflow rules do **not** use catalog `reads`; reads for R3/R4 live on the **spec node** (doc 04). The catalog `reads` is informational here.
- **No `config_schema`** — the proposable surface R2 type-checks against is `ToolCatalogDocument.proposable_params` (the params whose `config_origin == "literal"`). (Doc 03 also derives a typed `config_schema` property; R2 uses `proposable_params` + the `annotation` string per §5.1.)
- **No `reads_optional` on the catalog** — it lives on the spec node (`StepSpec.reads_optional`, doc 04). R3 exempts it from there.
- **The `invariant_tool` flag is NOT consulted (CC-2).** Doc 03's `ToolCatalogDocument` carries an `invariant_tool` boolean, but doc 05 **never reads it** — invariant detection is by **artifact writes only** (CC-2). R7 identifies the invariant-bearing tools by their declared **`writes`** (the tool whose catalog `writes` includes `SAFETY_VERDICT` is the guardian-bearing `compose_until_safe`; the tool whose catalog `writes` includes `PUBLISHED_POST` is `publish_post`). "Writes the invariant artifact" is precisely the property R7 asserts; the flag is redundant. See §4.

**Why the catalog (not the tool files) and the spec node are the sources of truth:** tool `run()` signatures are introspected by doc 03 only for *parameter classification* (`ToolParameter`), never for the dataflow graph. The real per-step `reads`/`writes`/`config` live on the spec node (doc 04). The validator/compiler consume the `ToolCatalog` object + the spec node and never reflect on a `run` signature.

### 3.3 The adapter helpers (the only place sibling field names appear)

If doc 03/04 rename a field, change **only** the small accessor helpers at the top of each module. Everything else is written against these. Concrete bodies (so the implementer copies, not guesses):

```python
# shared accessors (define once, importable by both validator.py and compiler.py,
# e.g. in app/pipeline/spec/_spec_access.py — or duplicate the ~8 lines per module)

def _step_kind(node) -> str:
    # doc 04 leaf discriminant is "step"; normalize to "leaf" for internal use.
    k = node.kind
    return "leaf" if k == "step" else k          # "parallel" / "chain" pass through

def _step_tool_id(node) -> str | None:
    return getattr(node, "tool_id", None)

def _step_children(node) -> list:
    return getattr(node, "children", []) or []

def _step_config(node) -> dict:
    return getattr(node, "config", {}) or {}

def _step_reads(node) -> list[str]:
    return getattr(node, "reads", []) or []

def _step_writes(node) -> list[str]:
    return getattr(node, "writes", []) or []

def _step_reads_optional(node) -> list[str]:
    return getattr(node, "reads_optional", []) or []

def _tool(catalog, tool_id: str):
    # catalog is doc 03's ToolCatalog object (CC-1); it already indexes by tool_id.
    # This adapter exists only so a later rename of the lookup method is a one-line change.
    # Returns ToolCatalogDocument | None.
    return catalog.get(tool_id)
```

This keeps the rename blast-radius to ~8 one-line functions.

---

## 4. The invariants are the engine's, not the spec's (Decision Defense)

**The cost ceiling and the safety guardian are NON-BYPASSABLE and are NOT in the compiled `Step` tree.** This is the architecture's load-bearing rule and it directly shapes what the validator is allowed to check.

- The cost ceiling + guardian are injected by the **engine** as wrappers in `run_steps` around every leaf (doc 07). They are not expressible or removable in the spec, so the compiler **must not** emit a "cost step" or "guardian step", and the validator **must not** require one.
- What the validator *can* enforce is that the spec **uses the invariant-bearing catalog tools** at the right grain: the safety guardian is owned by the coarse `compose_until_safe` tool (which runs the irreducible compose→guardian→regenerate loop internally and writes `COMPOSED_POST` + `SAFETY_VERDICT`, doc 06 §5.1), and publish is owned by `publish_post` (which writes `PUBLISHED_POST` and carries the idempotency marker, doc 06 §5.2).
- **How R7 identifies these tools by artifact writes, not a flag (CC-2):** doc 03's `ToolCatalogDocument` does carry an `invariant_tool` boolean, but **doc 05 deliberately does not read it** — invariant detection is by artifact writes only (CC-2). Both ACT tools declare *static* `TOOL_WRITES`, so their `ToolCatalogDocument.writes` is concrete and unambiguous (`compose_until_safe → [composed_post, safety_verdict]`, `publish_post → [published_post]`). R7 keys off **"the tool whose catalog `writes` includes `SAFETY_VERDICT`"** (= the guardian-bearing compose tool) and **"the tool whose catalog `writes` includes `PUBLISHED_POST`"** (= the publish tool). A hand-rolled leaf cannot forge these: the only catalog tools that declare those writes are the two invariant-bearing tools, because the catalog is closed (the builder only wires existing tools — it never writes a new tool that could also declare `PUBLISHED_POST`). So "writes the invariant artifact via a catalog tool" is exactly as strong as the flag, sourced purely from the artifact a tool produces.
- So rule **R7** (§5) is: *a valid spec must contain at least one leaf whose catalog tool writes `SAFETY_VERDICT`, and the terminal `PUBLISHED_POST` writer must be a catalog tool that statically declares `PUBLISHED_POST` in its `writes`.* That asserts the guardian and cost ceiling cannot be **bypassed** (you cannot author a spec that publishes without going through the guardian-bearing and publish tools) **without** the validator pretending to know about wrappers it can't see.

This is the elegant split: the engine owns enforcement; the validator owns *"the spec is shaped so enforcement will happen"*. The two never overlap.

---

## 5. `validator.py` — the rules

`validate_spec(doc, catalog)` runs seven checks and returns a `ValidationReport`. The checks are ordered cheap→expensive and **all run** (we collect every error, we do not stop at the first — the builder wants the full list). Each produces zero or more `ValidationError` entries with a stable `code`.

```python
def validate_spec(doc, catalog) -> ValidationReport:
    # catalog is doc 03's ToolCatalog object (CC-1); look up via catalog.get(tool_id) / `in`.
    flat = _flatten_spec_leaves(doc.steps)        # pure: mirrors flatten_steps, returns (dotted_id, node) pairs
    errors: list[ValidationError] = []
    errors += _check_unknown_tools(flat, catalog)         # R1  (catalog.get / `in` + is_internal)
    errors += _check_config_types(flat, catalog)          # R2  (catalog.get(...).proposable_params)
    errors += _check_dangling_reads(flat)                 # R3  (union-of-upstream-writes; spec-node reads/writes)
    errors += _check_no_cycles(flat)                      # R4
    errors += _check_unique_ids(flat)                     # R5
    errors += _check_terminal_published(flat)             # R6  (spec-node writes only)
    errors += _check_invariants_present(flat, catalog)    # R7  (catalog.get(...).writes — artifact detection, CC-2)
    return ValidationReport(ok=not errors, errors=errors)
```

> Each rule that consults the catalog takes the `ToolCatalog` object and calls `catalog.get(tool_id)` (returning a `ToolCatalogDocument | None`) or `tool_id in catalog`; there is no pre-built `by_id` dict (the object already indexes by `tool_id`). R6 reads only the spec node's writes (CC-2 terminal detection); R7 reads `catalog.get(tool_id).writes` to confirm the writer is the invariant-bearing tool by the artifact it produces.

`_flatten_spec_leaves` mirrors `flow.flatten_steps` exactly (same dotted-id scheme `flowGraph.ts` couples to), but over spec nodes instead of `Step`s, returning the leaf node alongside its dotted id so the rules can read its config/reads/writes:

```python
def _flatten_spec_leaves(steps, parent_id: str | None = None) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for node in steps:
        full_id = f"{parent_id}.{node.id}" if parent_id else node.id
        if _step_kind(node) == "leaf":
            out.append((full_id, node))
        else:                                    # composite: id joins the prefix, it is not a leaf
            out.extend(_flatten_spec_leaves(_step_children(node), full_id))
    return out
```

> **R5 detects duplicates on the dotted id**, so two leaves named `rank` under *different* composites (`a.rank`, `b.rank`) do NOT collide, but two siblings sharing `id` do — matching how `flatten_steps` would render them. The order of `flat` is the execution order R3/R4/R6 walk.

> **Reads/writes come from the SPEC NODE, not the catalog.** R3/R4/R6 operate on `_step_reads(node)` / `_step_writes(node)` (doc 04 stores them on `StepSpec`; the seed copies them from the runbook). The catalog's `writes` is `None` for the dynamic-`store_key` rankers/briefs and its `reads` is `None` for every SENSE tool (doc 03) — so it cannot be the source for the dataflow rules. R1/R2/R7 are the only rules that consult the catalog (via `catalog.get` / `in`).
>
> **Internal-primitive sentinel (`_internal.*`) — `INTERNAL_PRIMITIVES` (CC-8).** Doc 04's seed maps `collect_external_references` to the sentinel `tool_id="_internal.collect_external"` (a pure interpreter primitive that promotes `SEARCH_REFERENCES` → `TIMELINE_REFERENCES`; it is NOT a catalog tool — verified `services/steps.py:90-114` calls no `tools/**`). Per CC-8 the closed table **`INTERNAL_PRIMITIVES` lives in this slice** (`app/pipeline/spec/internal_primitives.py`, §2) and both the validator and the compiler consult it:
> ```python
> # app/pipeline/spec/internal_primitives.py — OWNED BY DOC 05 (CC-8)
> from app.pipeline.services import steps
> from app.pipeline.types.artifacts import ArtifactKey
>
> INTERNAL_PRIMITIVES: dict[str, dict] = {
>     "_internal.collect_external": {
>         "run": steps.collect_external_references,        # compiler binds Step.run from this
>         "reads": (ArtifactKey.SEARCH_REFERENCES,),
>         "writes": (ArtifactKey.TIMELINE_REFERENCES,),
>     },
> }
>
> def is_internal(tool_id: str | None) -> bool:
>     return bool(tool_id) and tool_id in INTERNAL_PRIMITIVES
> ```
> R1 treats an `_internal.*` id as **known** (no `unknown_tool`); R2 treats it as **having no proposable config** (any config key on an internal leaf → `config_unknown_key`; the seed gives it empty config, so it passes). R3/R4/R6 use its **spec-node** `reads`/`writes` (the seed carries `reads=[search_references]`, `writes=[timeline_references]`), so the dataflow rules grade it correctly without a catalog entry. R7 ignores it (it writes neither `SAFETY_VERDICT` nor `PUBLISHED_POST`). The compiler binds it to `INTERNAL_PRIMITIVES["_internal.collect_external"]["run"]` = `steps.collect_external_references` directly (§6.0). This is the resolution doc 04 §7 deferred to here: keep it an interpreter primitive, register it in one table both pure modules share, never fake a catalog tool.

| # | Code | Rule | How it is checked |
|---|---|---|---|
| R1 | `unknown_tool` | Every leaf's `tool_id` exists in the catalog **or is a recognized `_internal.*` primitive**. | `tool_id not in catalog and not is_internal(tool_id)` → `unknown_tool` (CC-8: R1 skips the catalog-membership check for `_internal.*`). Composites are skipped (use `_step_kind(node) == "leaf"`). A leaf with `tool_id is None` → `missing_tool_id`. |
| R2 | `config_type_mismatch` / `config_unknown_key` / `config_missing_required` | Each leaf config value type-checks against the tool's **proposable** params; unknown/non-proposable keys and missing required proposable fields are flagged. | `tool = catalog.get(tool_id)`; `props = {p.name: p for p in tool.proposable_params} if tool else {}` (doc 03: params with `config_origin == "literal"`; `tool is None` for the `_internal.*` sentinel → empty props). For each `(key, raw)` in `_step_config(node)`: if `key not in props` → `config_unknown_key` (this rejects *both* truly unknown keys AND non-proposable keys like `store_key`/`source`, which are `config_origin=="wired"` and so absent from `proposable_params` — treated as compile-time wiring per doc 04, never spec config); else `_typecheck(raw, _param_type(p))` → on False, `config_type_mismatch`. After the loop, any `props` field with `p.required` and no default, absent from config → `config_missing_required`. Internal-sentinel (`tool is None`) and ACT leaves (`proposable_params == []`): any config key → `config_unknown_key`; the seed gives them empty config, so they pass. R2 only consults the catalog — skip it entirely when a prior R1 already flagged the `tool_id` as `unknown_tool` to avoid a redundant `config_unknown_key` cascade on a typo'd tool. |
| R3 | `dangling_read` | Every leaf reads only artifacts in the **union of all upstream writes** (every write that appears strictly earlier in flatten order), excluding the leaf's own `reads_optional`. | Walk `flat` in order, accumulating `produced: set[str]` from each leaf's **spec-node** `_step_writes(node)`. For leaf *i*, every `r in _step_reads(node_i)` must be in `produced_before_i`. `reads_optional` (`_step_reads_optional(node)`) are exempt (matches the engine: optional reads are not enforced — verified `flow.py:26`, `_runbook_engine.py:55`). Reads/writes are compared as `ArtifactKey.value` strings; an unrecognized string (not in `ArtifactKey`) is itself a `dangling_read` (nothing can produce it). |
| R4 | `cycle` | No artifact dependency cycle. | Because spec steps execute in flatten order and reads must be satisfied by *strictly earlier* writes (R3), a forward-only flatten order is acyclic by construction. R4 catches the one residual case R3 misses: a leaf that **reads an artifact only ever written by itself or a later step** (forward reference). Build a producer index `first_writer[key] = first flatten index that writes key` (from spec-node `_step_writes`); for leaf *i* reading required `r`, if `first_writer.get(r, +inf) >= i` → `cycle` (it depends on itself-or-later). R3 reports the *missing-upstream* framing; R4 reports the *self/forward* framing — emit whichever matches so the builder gets the precise reason, never both for the same `(leaf, artifact)`. |
| R5 | `duplicate_step_id` | Dotted leaf ids are unique. | The dotted ids from `_flatten_spec_leaves` must be distinct; a collision means two siblings share an `id`. |
| R6 | `no_terminal_published` | Exactly one terminal step writes `PUBLISHED_POST`, and it is the **last** leaf in flatten order. | Collect leaves whose **spec-node** `_step_writes(node)` includes `ArtifactKey.PUBLISHED_POST.value`. Zero → `no_terminal_published`. The last such leaf must be the last leaf overall; if any leaf executes *after* the publishing leaf → `step_after_publish` on that later leaf. |
| R7 | `missing_safety_invariant` / `missing_publish_invariant` | The guardian-bearing tool and the publish tool are present and not bypassed. | Detection is by **artifact writes only (CC-2)** — never the `invariant_tool` flag. At least one leaf whose `catalog.get(tool_id).writes` includes `safety_verdict` must exist (→ guardian-bearing `compose_until_safe` present). The terminal `PUBLISHED_POST` writer's `catalog.get(tool_id).writes` must statically include `published_post` (→ publish goes through the idempotent, cost-wrapped `publish_post`, not a hand-rolled leaf). For R7 the catalog `writes` is authoritative because both ACT tools declare *static* `TOOL_WRITES` (doc 06 §5); an `_internal.*` or unknown leaf has no catalog entry and thus cannot satisfy R7. Missing either → the corresponding code. |

> **R7 uses catalog `writes`, R6 uses spec-node `writes` — and that is deliberate.** R6 asks "is there a terminal step the *spec* declares as writing `PUBLISHED_POST`, with nothing after it" — a structural/ordering question answered from the spec. R7 asks "is that terminal writer *actually* the invariant-bearing `publish_post` catalog tool, not a leaf that merely declares the write" — an identity question answered from the catalog (`catalog.get(tool_id).writes`). A spec could declare `writes=[published_post]` on a `data.account_profile` leaf (R6 passes), but R7 then fails `missing_publish_invariant` because `account_profile`'s catalog `writes` is `[account_bundle]`, not `[published_post]`. The two rules together make publish un-forgeable.

> **R3 vs R4 are intentionally separate codes** even though one acyclic forward-only ordering makes them closely related. R3 is the user-facing "this step reads `X` but nothing before it produces `X`" (the common authoring mistake — a deleted upstream step). R4 is the rarer "this step's only producer of `X` is itself or downstream" (a reordering mistake). Reporting them distinctly is the difference between a builder that can self-repair and one that guesses. They are mutually exclusive per `(leaf, artifact)` by the index check above.

### 5.1 Config type-checking (`_param_type` + `_typecheck`)

The catalog (doc 03) does not give a clean `Literal["int",…]` type per param — it gives `ToolParameter.annotation` (a raw annotation **string** like `"int"`, `"int | None"`, `"list[str]"`, because every tool module uses `from __future__ import annotations`; verified doc 03 §2.1). So R2 first normalizes that annotation string to one of our checkable type names, then type-checks. Both helpers are pure, no coercion — the config value as authored must already be the right JSON type:

```python
# Normalize a raw annotation STRING (doc 03 ToolParameter.annotation) to a checkable name.
# Strips an optional "| None" and lowercases; the proposable surface today is small
# (top_n:int, max_results_per_query:int|None, the 4 compose soul fields:str/list) so the
# closed mapping below covers every literal param. Unrecognized → "" (R2 skips type-check,
# only key membership is enforced — we never reject a value we cannot model).
def _param_type(p) -> str:
    ann = (p.annotation or "").replace("| None", "").replace("|None", "").strip().lower()
    return {
        "int": "int", "float": "float", "str": "str", "bool": "bool",
        "list[str]": "list[str]", "list": "list[str]", "dict": "dict",
        "dict[str, any]": "dict",
    }.get(ann, "")

_PY_TYPE = {
    "str": str, "int": int, "float": (int, float), "bool": bool,
    "list[str]": list, "dict": dict,
}
def _typecheck(raw, type_name: str) -> bool:
    if not type_name:                   # annotation we don't model → don't reject the value
        return True
    py = _PY_TYPE.get(type_name)
    if py is None:
        return True
    # JSON has no int/float distinction for bools: reject bool where int/float expected.
    # (Check BEFORE isinstance because bool IS an int subclass in Python.)
    if type_name in ("int", "float") and isinstance(raw, bool):
        return False
    if not isinstance(raw, py):
        return False
    if type_name == "list[str]":
        return all(isinstance(x, str) for x in raw)
    return True
```

The `bool`-is-not-`int` guard matters: in Python `isinstance(True, int)` is `True`, so without it `top_n: True` would pass an `int` field. The only numeric proposable today is `top_n` (verified: `reference_rank.run(..., top_n: int = 10, ...)` at `tools/deterministic/reference_rank.py:23-29`; doc 03 surfaces it as a `ToolParameter(name="top_n", annotation="int", config_origin="literal")`). Note `top_n` is wired into **two** ranker sites in the live wrappers — `rank_external_references` (`steps.py:138`) and `rank_own_posts` (`steps.py:214`) — so a spec may legally set `top_n` on either ranker step; both resolve to the same `deterministic.reference_rank` catalog tool.

### 5.2 `ValidationReport` shape (returned to the builder)

```python
# app/pipeline/spec/validator.py
from pydantic import BaseModel

class ValidationError(BaseModel):
    code: str            # stable machine code (table above)
    step_id: str | None  # dotted id of the offending leaf; None for whole-spec errors (R6 zero-publish)
    artifact: str | None = None   # ArtifactKey.value when the error is artifact-scoped (R3/R4)
    detail: str = ""     # human-readable, e.g. "reads 'composed_post' but no upstream step writes it"

class ValidationReport(BaseModel):
    ok: bool
    errors: list[ValidationError]

    def codes(self) -> list[str]:
        return [e.code for e in self.errors]
```

The full stable code set the builder (doc 10), the self-rewrite loop (doc 09), and tests switch on:

```
unknown_tool, missing_tool_id,
config_type_mismatch, config_unknown_key, config_missing_required,
dangling_read, cycle, duplicate_step_id,
no_terminal_published, step_after_publish,
missing_safety_invariant, missing_publish_invariant
```

`ValidationReport` is a Pydantic model so the builder can serialize it straight into an SSE/JSON error payload — doc 10 §6 streams it as the `validation_errors` event `{code, step_id, artifact, detail}` and doc 09 §5.1 branches on `report.ok`. `ok` is redundant with `not errors` but is kept because callers branch on `report.ok` and an explicit boolean reads cleaner at the call site than `not report.errors`.

---

## 6. `compiler.py` — lowering spec → `Step` tree

`compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` walks `doc.steps` and rebuilds the `Step` tree using the **same** `chain()`/`parallel()` helpers the hand-written runbook uses, binding each leaf to the **`services/steps.py` wrapper** for its tool.

> **Naming:** the public function is `compile_spec` (not `compile`) to avoid shadowing the Python built-in `compile`. The brief says "`compile(doc)`"; we keep the intent and use the unambiguous name, re-exported from `spec/__init__.py`. (Same reasoning the codebase uses elsewhere to avoid stdlib shadowing.)

The compiler needs two things per leaf: (1) the **callable** to bind as `Step.run`, and (2) the **declared `reads`/`writes`/`reads_optional`** for the `Step`. Per the §3 reconciliation:
- `reads`/`writes`/`reads_optional` come from the **spec node** (`_step_reads`/`_step_writes`/`_step_reads_optional`), parsed `.value` string → `ArtifactKey`. They are NOT on the catalog. This is the same source the hand-written runbook leaves declare, so the compiled `Step` is identical.
- the **callable** is the `services/steps.py` wrapper that the runbook already uses for that tool — resolved by a fixed step-id → wrapper map (§6.0). The catalog's introspected metadata is NOT a callable; the engine runs the wrapper `(ctx, deps) -> StepResult`, exactly as today. (Doc 03's `ToolCatalog.run_for(tool_id)` also exposes a bound wrapper, but it returns `None` for the two *shared* tools — `reference_rank`/`reference_pattern_summary` — so the compiler keeps its own step-id-keyed map to disambiguate them, §6.0.)

`catalog` defaults to `None` and the body falls back to `get_tool_catalog()` (CC-1: the single factory) for the one-arg ergonomics the brief asks, but is injectable for tests — mirroring how `PostRunDeps.build()` resolves its defaults. The catalog is used by the compiler only for `purpose` fallback and to confirm `tool_id` resolves; the dataflow comes from the spec node.

```python
def compile_spec(doc, *, catalog: "ToolCatalog | None" = None) -> tuple[Step, ...]:
    cat = catalog if catalog is not None else get_tool_catalog()   # CC-1: the single factory
    return tuple(_compile_node(n, cat) for n in doc.steps)

def _compile_node(node, cat) -> Step:
    kind = _step_kind(node)
    if kind == "leaf":
        tool_id = _step_tool_id(node)               # R1 guarantees catalog-or-_internal post-validate
        run = _wrapper_for(node)                     # §6.0/§6.2 — keys on node.id, validates node.tool_id
        tool_doc = cat.get(tool_id)                 # ToolCatalog.get; None for _internal.* (no catalog entry)
        return Step(
            id=node.id,
            run=run,
            reads=_keys(_step_reads(node)),                 # spec node → tuple[ArtifactKey]
            writes=_keys(_step_writes(node)),
            reads_optional=frozenset(_keys(_step_reads_optional(node))),
            purpose=node.purpose or (tool_doc.purpose if tool_doc else ""),
            composite_kind="leaf",
        )
    children = tuple(_compile_node(c, cat) for c in _step_children(node))
    if kind == "parallel":
        return parallel(*children, id=node.id, purpose=node.purpose)
    return chain(*children, id=node.id, purpose=node.purpose)

def _keys(values: list[str]) -> tuple[ArtifactKey, ...]:
    # spec stores ArtifactKey .value strings; lift back to enum members (validator already
    # guaranteed they are valid keys for non-optional reads/writes via R3).
    return tuple(ArtifactKey(v) for v in values)
```

### 6.0 The `tool_id → wrapper` map (the callable source)

The catalog's `ToolCatalogDocument` is *introspected metadata* — it carries no callable. The thing the engine actually runs is the `services/steps.py` wrapper, and each runbook leaf already maps 1:1 to one wrapper. The compiler reuses that exact map. It is keyed by **the runbook step id** (the inverse direction of doc 04 §7's `STEP_TOOL_MAP`, which goes step-id → tool-id): a `tool_id → callable` map would be ambiguous because multiple step ids share a tool — `rank_external_references` and `rank_own_posts` both use `deterministic.reference_rank` via *different* wrappers. So the binding is keyed by the spec node's `id`, with the paired `tool_id` as the integrity check:

```python
# app/pipeline/spec/compiler.py
from app.pipeline.services import steps   # the existing wrapper module (verified)

# spec-node id  ->  (expected tool_id, services/steps.py wrapper callable)
# Verified against runbooks/post_tick.py:20-85 + services/steps.py.
_WRAPPER_BY_STEP_ID = {
    "load_account_bundle":         ("data.account_profile",          steps.load_account_bundle),
    "fetch_search_references":     ("data.search_fetch",             steps.fetch_search_references),
    "collect_external_references": ("_internal.collect_external",    steps.collect_external_references),
    "fetch_own_post_history":      ("data.own_posts_fetch",          steps.fetch_own_post_history),
    "rank_external_references":    ("deterministic.reference_rank",  steps.rank_external_references),
    "brief_external_references":   ("llm.reference_pattern_summary", steps.brief_external_references),
    "rank_own_posts":              ("deterministic.reference_rank",  steps.rank_own_posts),
    "brief_own_posts":             ("llm.reference_pattern_summary", steps.brief_own_posts),
    # ACT tail (doc 06 adds these wrappers to services/steps.py — present once doc 06 lands):
    "compose_until_safe":          ("llm.compose_until_safe",        getattr(steps, "compose_step", None)),
    "publish_post":                ("data.publish_post",             getattr(steps, "publish_step", None)),
}
```

**Decision — bind by the runbook step id, not by `tool_id` alone.** Two different wrappers (`rank_external_references`, `rank_own_posts`) call the *same* `deterministic.reference_rank` tool with different `store_key`/`rows` wiring (verified `steps.py:135-140` vs `211-216`). A `tool_id → callable` map could not distinguish them; the **step id** does, and it is exactly what the runbook uses. This keeps the compiled leaf byte-identical to the hand-written one. The paired `tool_id` in the map is asserted equal to the spec node's `tool_id` at compile time (a cheap integrity check that catches a spec whose `id` and `tool_id` disagree — which validation does not forbid but the seed never produces).

> **The `_internal.collect_external` row defers to `INTERNAL_PRIMITIVES` (CC-8 — single source of truth).** The `collect_external_references` entry above shows the callable for readability, but the binding is sourced from the shared `INTERNAL_PRIMITIVES` table (§5) so the primitive's `run`/`reads`/`writes` are declared in exactly one place both pure modules read. Concretely, `_wrapper_for` resolves an `_internal.*` `tool_id` via `INTERNAL_PRIMITIVES[tool_id]["run"]` (= `steps.collect_external_references`, CC-8) *before* consulting `_WRAPPER_BY_STEP_ID`; the map row is the same callable, kept only so the step-id table reads as a complete inventory.

> **Why a map and not "the catalog supplies the callable":** doc 03 deliberately does NOT put a callable in `ToolCatalogDocument` (it is JSON-dumpable metadata, hashable, never a function). The real wiring lives in `services/steps.py` (the house pattern: "the real wiring logic lives in `services/steps.py` wrappers, not in the tools"). The compiler honors that boundary — it selects the existing wrapper, it does not synthesize one.

### 6.1 Reproducing the exact `flatten_steps` dotted-id scheme

This is the graded property. `flatten_steps` (verified, `flow.py:103-124`) builds dotted ids by prefixing a composite's id onto its descendants: `f"{parent_id}.{step.id}"`, recursing through `_flatten_one`. Composites contribute their `id` to the prefix but are **not** themselves leaves in the output.

The compiler reproduces this **for free** by construction: it uses `node.id` verbatim as each `Step.id` and uses `parallel()`/`chain()` to assemble composites with `id=node.id`. Since the engine's `flatten_steps` is the *same function* that will later flatten the compiled tree, the dotted ids are identical **iff the spec's nested ids match the runbook's nested ids**. So the requirement reduces to: doc 04's seed/baseline spec must carry the same ids the hand-written runbook uses, namely (verified against `runbooks/post_tick.py:20-85`):

```
load_account_bundle
fetch_search_references
collect_external_references
fetch_own_post_history
summarize_for_compose                         (parallel)
  analyze_external_references                 (chain)
    rank_external_references
    brief_external_references
  analyze_own_posts                           (chain)
    rank_own_posts
    brief_own_posts
```

→ flatten output (the exact strings `flowGraph.ts` matches):

```
load_account_bundle
fetch_search_references
collect_external_references
fetch_own_post_history
summarize_for_compose.analyze_external_references.rank_external_references
summarize_for_compose.analyze_external_references.brief_external_references
summarize_for_compose.analyze_own_posts.rank_own_posts
summarize_for_compose.analyze_own_posts.brief_own_posts
```

The compiler does **not** re-implement dotting; it must not. The lock test (§8) compiles the baseline spec and asserts `flatten_steps(compile_spec(baseline)) == flatten_steps(POST_TICK_REFERENCE_STEPS)` id-for-id. If that passes, the dashboard nodes light up unchanged.

> **Why reuse `chain`/`parallel` instead of constructing composite `Step`s directly:** those helpers also compute the composite's aggregate `reads`/`writes`/`reads_optional` via set-union (`flow.py:48-91`) and wire `run=_run_children(...)`. Reconstructing that by hand would duplicate engine logic and drift. Calling the helpers is the elegant path and keeps composite semantics identical to the hand-written runbook.

### 6.2 Binding config into the leaf `run` (`_wrapper_for`)

The wrappers in `services/steps.py` are `(ctx, deps) -> StepResult` with **no config kwarg today** (verified — `load_account_bundle` ln 38, `rank_external_references` ln 123, etc.), and every config value is hardcoded inside the wrapper (`top_n=MIN_TOP_N` at **both** `steps.py:138` and `steps.py:214`; `max_results_per_query=SEARCH_RESULTS_PER_NICHE` at `steps.py:86`). For a spec's `config` to actually reach a tool, the wrapper must read it. This slice does the **minimal, surgical** version of that and **owns it** (no deferral to an unowned doc):

**Decision — pass config via the run context under a reserved per-step key, and have the *baseline* compile to the verbatim wrapper.** The compiler never changes a wrapper's signature; it sets the step's config on `ctx.data` under a reserved namespaced key just before the wrapper runs, and the wrapper reads it with a fallback to its existing hardcoded constant. This keeps the wrapper a single `(ctx, deps)` function (the house pattern) and keeps the compiler a pure transform.

```python
_STEP_CONFIG_PREFIX = "_step_config:"   # reserved ctx.data namespace; never an ArtifactKey

def _wrapper_for(node):
    # CC-8: an _internal.* leaf binds its run from the shared INTERNAL_PRIMITIVES table,
    # not the catalog. It carries no proposable config (R2), so it always binds verbatim.
    if is_internal(node.tool_id):
        return INTERNAL_PRIMITIVES[node.tool_id]["run"]   # steps.collect_external_references
    expected, wrapper = _WRAPPER_BY_STEP_ID[node.id]   # keyed on the runbook step id (§6.0)
    if wrapper is None:                  # ACT wrappers absent until doc 06 — should not occur for SENSE
        raise ValueError(f"no wrapper for step {node.id!r} (tool {node.tool_id!r})")
    if expected != node.tool_id:         # integrity check: id and tool_id must agree
        raise ValueError(f"step {node.id!r} maps to {expected!r}, spec says {node.tool_id!r}")
    cfg = _step_config(node)
    if not cfg:
        return wrapper                   # empty config → the wrapper verbatim (byte-identical to today)
    key = _STEP_CONFIG_PREFIX + node.tool_id
    def _run(ctx, deps):
        ctx.data[key] = dict(cfg)
        try:
            return wrapper(ctx, deps)
        finally:
            ctx.data.pop(key, None)
    return _run
```

The binder keys on `node.id` (the runbook step id, which uniquely identifies the wrapper — see §6.0 on why `rank_external_references` vs `rank_own_posts` must be distinguished) and asserts the mapped `tool_id` matches the spec node's `tool_id`. The reserved `ctx.data` key is namespaced by `tool_id` so the wrapper's `_cfg(ctx, "<tool_id>")` (below) reads exactly what was set.

> **Two steps sharing a `tool_id` (both rankers use `deterministic.reference_rank`) do NOT collide on the reserved key.** Steps run strictly sequentially (`flow._run_children` and `_runbook_engine.run_steps` iterate one leaf at a time — verified), and the `try/finally` pops the key the instant the wrapper returns. So `rank_external_references` sets→reads→pops `_step_config:deterministic.reference_rank` entirely before `rank_own_posts` (with possibly different `top_n`) sets it again. The key is live only for the duration of one wrapper call.

**The matching wrapper edit (owned by THIS slice — two ranker sites + search, surgical):** each proposable-config wrapper reads its knob from the reserved key with the existing constant as the default, so behavior is unchanged when no config is present:

```python
# services/steps.py — example for rank_external_references (mirror at rank_own_posts:214,
# and at fetch_search_references:86 for max_results_per_query)
def _cfg(ctx, tool_id: str) -> dict:
    return ctx.data.get("_step_config:" + tool_id, {})

def rank_external_references(ctx, deps):
    ...
    cfg = _cfg(ctx, "deterministic.reference_rank")
    return reference_rank.run(
        ctx, rows=pool,
        top_n=int(cfg.get("top_n", MIN_TOP_N)),                 # was: top_n=MIN_TOP_N (steps.py:138)
        store_key=ArtifactKey.TIMELINE_RANKED.value,
    )
```

> **Why the ctx-key channel over a `config=` kwarg on every wrapper.** A `config` kwarg would force the runbook's hand-written `Step`s (which call the same wrappers with NO config) to either pass `config={}` everywhere or rely on a default — and it would change every wrapper's signature, widening the diff to all 8 SENSE wrappers plus the 2 ACT wrappers even though only **3** proposable knobs exist (`top_n` ×2 sites, `max_results_per_query` ×1). The reserved-ctx-key channel touches only the 3 wrappers that have a literal knob, leaves the other wrappers' signatures untouched, and the compiler binds the verbatim wrapper whenever config is empty (the baseline case). It is the smaller, more surgical change — and the reserved key (`_step_config:` prefix) can never collide with an `ArtifactKey` (those are bare lowercase identifiers; `set_artifact` only ever writes `ArtifactKey.value`).

When `cfg` is empty the compiled leaf is **identical** to today's hand-written step (the same wrapper callable object), so a baseline spec compiles to a behaviorally-identical pipeline — the cleanest possible proof the lowering is faithful. The §8 lock test asserts this (`compiled_leaf.run is steps.<wrapper>` for an empty-config leaf).

> **Scope note — the ACT tools (`compose_until_safe`/`publish_post`) have NO proposable config.** Their wrappers (`compose_step`/`publish_step`, doc 06 §7.2) are `(ctx, deps)` pass-throughs and `proposable_params == []`, so R2 rejects any config key on them and the compiler always binds them verbatim (the `if not cfg` branch). There is no config plumbing for the coarse tools — by design (the brief: the guardian/cost invariants are engine-injected, never spec config).

---

## 7. Decision Defense (non-obvious choices)

**Why a pure validator separate from the compiler, rather than a compiler that raises?**
The builder calls `validate_spec` to get a *list* of every problem (so it can self-repair or show the user all errors at once); a raise-on-first-error compiler gives one error per round-trip. Keeping them separate also means `compile_spec` can assume a validated spec and stay tiny (no defensive re-checking). The builder's contract is: `validate_spec` first; only `compile_spec` if `report.ok`.

**Why does the validator take `catalog` as a parameter instead of importing it?**
Purity + testability. `validate_spec(doc, catalog)` with no module-level catalog import is deterministic and trivially unit-testable with a fixture `ToolCatalog` — no monkeypatching, no global state. The compiler defaults its catalog to `get_tool_catalog()` (for the one-arg ergonomics the brief asks) but still accepts an override for the same reason. This mirrors how the rest of the pipeline injects deps rather than reaching for globals (`PostRunDeps.build()`), and matches the call sites: doc 09 §5.1 and doc 10 §3.6 both pass `get_tool_catalog()` (the `ToolCatalog` object, CC-1) explicitly.

**Why assert the *terminal* `PUBLISHED_POST` writer is the last leaf (R6 `step_after_publish`)?**
Publish is non-idempotent against X (verified: `interval/orchestration/post_tick.py:36` calls `ctx.twitter.post_tweet` once, no idempotency marker today; **doc 06 §5.2** adds the `(run_id, account_id)` idempotency ledger). A spec that schedules any leaf *after* the publish is either dead work or a second publish. Forbidding anything after the terminal publish is the static guarantee that the pipeline ends at exactly one post. This is cheap to check in flatten order and impossible to express as a pure "dangling read" rule, so it earns its own code.

**Why check invariants by the catalog tool's declared `writes` (R7) instead of by spec-node artifact alone, and why not the `invariant_tool` flag?**
Checking only "*the spec declares* something writes `SAFETY_VERDICT`" would let a hand-rolled leaf forge the verdict and skip the real guardian/regeneration loop (a `data.account_profile` leaf could declare `writes=[safety_verdict]`). Requiring that the writer be the catalog tool whose *static* `TOOL_WRITES` includes `SAFETY_VERDICT` (= `compose_until_safe`) ties the verdict to the tool that actually runs the guardian internally and cannot be decomposed (the compose loop is irreducibly imperative — verified `interval/runner.py:304-365`, owned by doc 06 §5.1). The catalog's static `writes` is the closed-set promise; the validator just asserts the promise is used. The cost ceiling rides the same wrappers in `run_steps` (doc 07) and is therefore enforced for *every* leaf regardless of spec — so there is nothing for the validator to check about cost beyond "publish goes through the cost-wrapped `publish_post` tool", which R7's catalog-`writes` requirement on the terminal writer already covers. **Per CC-2, invariant detection is by artifact writes only.** Doc 03's `ToolCatalogDocument` does carry an `invariant_tool` boolean, but doc 05 deliberately does not consult it — the static `writes` of the two closed ACT tools is an exactly-equivalent signal sourced purely from the artifact each produces, so R7 needs no flag (see §4).

**Why `reads_optional` is exempt from the dangling-read check.**
The engine does not enforce optional reads (verified: `flow.py:26` declares `reads_optional`; `_runbook_engine.py:55` captures them for tracing but never fails on absence; steps guard with `ctx.has_artifact`). Failing a spec for an unsatisfied *optional* read would be stricter than the runtime and would reject legitimate specs (e.g. `brief_own_posts` reading `OWN_POSTS` which may be skipped). The validator matches runtime semantics exactly.

**Why `compile_spec` reuses `flatten_steps` semantics rather than emitting dotted ids itself.**
Single source of truth for the id scheme. The frontend already couples to `flatten_steps` output; if the compiler grew its own dotting it could drift from the engine's. By emitting a plain `Step` tree and letting the *same* `flatten_steps` produce ids at run time, there is exactly one dotting implementation. The compiler's only job is to nest ids correctly, which the §8 lock test pins.

---

## 8. Tests

### Fixtures (self-contained — no dependency on doc 06 landing first)

Three fixtures live in `tests/unit/pipeline/conftest.py`:

- **`sense_baseline_spec(account_id="JohnJames_News")`** — the **8-leaf SENSE-only** baseline, built **directly from the SENSE subtree of `POST_TICK_REFERENCE_STEPS`** by the same `_node_to_spec` walk doc 04 §7 uses, restricted to the SENSE steps:
  ```python
  from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
  from app.services.pipeline_spec_seed import _node_to_spec   # doc 04 §7 walker
  _SENSE_IDS = {"load_account_bundle", "fetch_search_references",
                "collect_external_references", "fetch_own_post_history",
                "summarize_for_compose"}
  def sense_baseline_spec(account_id="JohnJames_News"):
      sense = tuple(s for s in POST_TICK_REFERENCE_STEPS if s.id in _SENSE_IDS)
      return PipelineSpecDocument(account_id=account_id,
                                  steps=[_node_to_spec(s) for s in sense])
  ```
  This 8-leaf SENSE-only spec is a **building block** for `valid_act_spec` (the 10-leaf lock subject) and the SENSE-prefix robustness anchor — not the lock subject itself. Building it directly from the SENSE subtree (rather than calling `spec_from_runbook`) keeps it byte-stable whether `POST_TICK_REFERENCE_STEPS` currently has 8 leaves (pre-doc-06) or 10 (post-doc-06), and never trips on `STEP_TOOL_MAP` lacking an ACT entry. (Do NOT call `spec_from_runbook` here — that walks the *whole* runbook and would `KeyError` on the ACT leaves until doc 06/04 add them to `STEP_TOOL_MAP`; that seed-append coordination is doc 04/06's, not this slice's.)
- **`fixture_catalog()`** — a hand-built `ToolCatalog` object (CC-1) covering the 6 SENSE tools + `llm.compose_until_safe` + `data.publish_post`, mirroring doc 06 §5's declared `TOOL_WRITES` (`compose_until_safe → ["composed_post","safety_verdict"]`, `publish_post → ["published_post"]`) and the proposable params (`top_n:int`, `max_results_per_query:int`). Build it as `ToolCatalog([<ToolCatalogDocument…>])` (or `ToolCatalog(tools=[...])` per doc 03's ctor) so tests exercise the same `.get`/`__contains__` surface the real `validate_spec`/`compile_spec` callers pass — constructed inline so these tests need only doc 03's *model* + `ToolCatalog` class (which land before this slice), not doc 03/06's introspection modules on disk.
- **`valid_act_spec()`** — the **10-leaf baseline** (CC-6): `sense_baseline_spec()` **plus** the two ACT leaves appended to `steps` after `summarize_for_compose`: `compose_until_safe` (`tool_id="llm.compose_until_safe"`, reads `["timeline_analysis","own_posts_analysis","timeline_ranked"]`, writes `["composed_post","safety_verdict"]`) and `publish_post` (`tool_id="data.publish_post"`, reads `["composed_post","safety_verdict"]`, writes `["published_post"]`). These are bare top-level leaves (matching doc 06 §7.1's runbook append). This is the engine-runnable baseline R6/R7 require; it is **both** the happy-path validator input **and** the dotted-id lock subject (CC-6).

> **Note — `compose_until_safe.reads` is the canonical 3-tuple `(timeline_analysis, own_posts_analysis, timeline_ranked)` (doc 06 §7.1, the authoritative read set).** All three are written strictly upstream (`timeline_ranked` by `rank_external_references`), so R3 passes. doc 04 §7's `ACT_TAIL_SPECS` must carry the same three reads for the seed to grade identically; the fixture here mirrors doc 06 §7.1 verbatim.

### `test_spec_compiler.py` — the dotted-id lock (the runbook's requested regression)

The lock compiles the **10-leaf baseline** (`valid_act_spec`, CC-6) and asserts its flattened ids equal the canonical 10 dotted ids — the 8 SENSE ids `flatten_steps(POST_TICK_REFERENCE_STEPS)` produces plus the two ACT leaves. This is the exact id set the frontend `flowGraph.ts` fixture (doc 11) locks:

```python
_BASELINE_DOTTED = [
    "load_account_bundle", "fetch_search_references",
    "collect_external_references", "fetch_own_post_history",
    "summarize_for_compose.analyze_external_references.rank_external_references",
    "summarize_for_compose.analyze_external_references.brief_external_references",
    "summarize_for_compose.analyze_own_posts.rank_own_posts",
    "summarize_for_compose.analyze_own_posts.brief_own_posts",
    "compose_until_safe",
    "publish_post",
]

def test_compiled_baseline_matches_runbook_dotted_ids(valid_act_spec):
    # Scope: the 10-leaf baseline (CC-6). compile_spec binds the SENSE wrappers verbatim
    # and the two ACT wrappers via _WRAPPER_BY_STEP_ID (getattr-guarded pre-doc-06 — see below).
    compiled = compile_spec(valid_act_spec, catalog=fixture_catalog())
    got = [f.id for f in flatten_steps(compiled)]
    assert got == _BASELINE_DOTTED          # exact, ordered, string-for-string (10 ids)

def test_sense_prefix_matches_live_runbook():
    # Robustness anchor: the 8 SENSE dotted ids the compiler emits must equal the live
    # runbook's SENSE prefix, whether POST_TICK_REFERENCE_STEPS is 8 leaves (pre-doc-06)
    # or 10 (post-doc-06). Decoupled from the ACT lock so it never depends on the runbook
    # having grown the ACT leaves yet.
    want = [f.id for f in flatten_steps(POST_TICK_REFERENCE_STEPS)][:8]
    assert _BASELINE_DOTTED[:8] == want
```

> **Pre-doc-06 implementability of the 10-leaf lock.** Doc 05 lands before doc 06 (§4 order), so `steps.compose_step`/`steps.publish_step` may not exist on disk yet — `_WRAPPER_BY_STEP_ID`'s ACT rows use `getattr(steps, "compose_step", None)` (§6.0). The dotted-id lock only flattens the compiled tree (it reads each leaf's `id`, never invokes `run`), so a `None` ACT wrapper does **not** break it: `_wrapper_for` returns the `None` wrapper into the `Step.run` slot for the bare-config ACT leaves and `flatten_steps` still yields `compose_until_safe`/`publish_post`. Only a test that *executes* an ACT leaf needs the real wrapper, and there is none in this slice. (Once doc 06 lands, `getattr` resolves to the real `compose_step`/`publish_step` and nothing changes for the lock.)

Plus:
- `test_leaf_with_empty_config_binds_wrapper_verbatim` — asserts `compiled_leaf.run is steps.load_account_bundle` (the exact `services/steps.py` wrapper object) for an empty-config leaf.
- `test_leaf_with_config_threads_through` — a `rank_external_references` leaf with `config={"top_n": 5}` compiles to a closure (not the bare wrapper); running it against a fake `ctx`/`deps` records `_step_config:deterministic.reference_rank == {"top_n": 5}` on `ctx.data` for the duration of the call and pops it after.
- `test_composite_reads_writes_are_union` — asserts a compiled `parallel`/`chain` has the same aggregate `reads`/`writes`/`reads_optional` as the hand-written one (it must, since both go through `flow.chain`/`flow.parallel`).
- `test_internal_sentinel_binds_collect_wrapper` — the `collect_external_references` leaf (`tool_id="_internal.collect_external"`) compiles to `steps.collect_external_references` (bound via `INTERNAL_PRIMITIVES`, CC-8) and carries `reads=(SEARCH_REFERENCES,)`, `writes=(TIMELINE_REFERENCES,)` from the spec node.

### `test_spec_validator.py` — one assertion per code

All negative tests build on `valid_act_spec()` (which passes clean) and mutate one thing, then assert the expected code is present **and** that the mutation does not spuriously trip an unrelated code.

| Test | Builds a spec that… | Asserts code |
|---|---|---|
| `test_happy_path_act_baseline_ok` | is `valid_act_spec()` (SENSE + compose_until_safe + publish_post) | `report.ok is True`, `report.errors == []` |
| `test_unknown_tool` | leaf `tool_id="data.does_not_exist"` | `"unknown_tool" in codes` |
| `test_internal_sentinel_is_known` | the `_internal.collect_external` leaf | `"unknown_tool" not in codes` |
| `test_missing_tool_id` | leaf with `tool_id=None` (kind `"step"`) | `"missing_tool_id" in codes` |
| `test_config_type_mismatch` | `top_n: "ten"` (str into int param) | `"config_type_mismatch" in codes` |
| `test_config_bool_into_int_rejected` | `top_n: true` | `"config_type_mismatch" in codes` |
| `test_config_unknown_key` | `{"frobnicate": 1}` on a rank leaf | `"config_unknown_key" in codes` |
| `test_config_non_proposable_key_rejected` | `{"store_key": "x"}` (a `wired` param — compile-time wiring per doc 04, never spec config; absent from `proposable_params`) | `"config_unknown_key" in codes` |
| `test_config_missing_required` | omit a required proposable field (synthetic fixture tool with a required literal param) | `"config_missing_required" in codes` |
| `test_dangling_read` | a leaf reading `timeline_ranked` placed before its ranker | `"dangling_read" in codes` |
| `test_forward_reference_cycle` | a leaf reading an artifact only it writes | `"cycle" in codes` |
| `test_duplicate_step_id` | two sibling leaves share `id` | `"duplicate_step_id" in codes` |
| `test_no_terminal_published` | `valid_act_spec()` with the `publish_post` leaf removed | `"no_terminal_published" in codes` |
| `test_step_after_publish` | a leaf scheduled after `publish_post` | `"step_after_publish" in codes` |
| `test_missing_safety_invariant` | publish present, `compose_until_safe` removed | `"missing_safety_invariant" in codes` |
| `test_missing_publish_invariant` | terminal leaf declares `writes=[published_post]` but `tool_id="data.account_profile"` (catalog `writes != [published_post]`) | `"missing_publish_invariant" in codes` |

> `test_config_missing_required` uses a synthetic fixture-catalog tool carrying one required `literal` param, because **no live tool has a required proposable param** (verified: `top_n` and `max_results_per_query` both have defaults). The code path must still be reachable and tested; the synthetic tool keeps the rule honest without faking the live catalog.

---

## 9. Definition of Done (per slice)

**Validator slice**
- `app/pipeline/spec/validator.py` exists; `validate_spec(doc, catalog) -> ValidationReport` is pure (no imports of services, RavenDB, or the engine; importing the module triggers no I/O). `catalog` is doc 03's `ToolCatalog` object (CC-1; looked up via `catalog.get`/`in`).
- `app/pipeline/spec/internal_primitives.py` exists with `INTERNAL_PRIMITIVES` + `is_internal` (CC-8); both `validator.py` and `compiler.py` import it.
- All seven rules implemented; every code in §5.2 is reachable and has a test. R7 detects invariants by artifact writes only (CC-2) — the `invariant_tool` flag is never read.
- `report.ok is True` and `report.errors == []` on `valid_act_spec()` (the 10-leaf baseline); each negative test yields exactly its expected code and no spurious extras.
- `reads_optional` never produces a `dangling_read`.
- The `_internal.collect_external` sentinel passes R1 (known via `INTERNAL_PRIMITIVES`) and grades R3/R4/R6 via its spec-node reads/writes.

**Compiler slice**
- `app/pipeline/spec/compiler.py` exists; `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` is pure (`catalog` is the doc 03 `ToolCatalog` object; defaults to `get_tool_catalog()` when `None`).
- `flatten_steps(compile_spec(valid_act_spec)) == _BASELINE_DOTTED` id-for-id (the 10-leaf lock test passes, CC-6), and the SENSE prefix equals `flatten_steps(POST_TICK_REFERENCE_STEPS)[:8]`.
- A leaf with empty config compiles to the `services/steps.py` wrapper object verbatim (`compiled.run is steps.<wrapper>`).
- A leaf with non-empty proposable config compiles to a closure that threads `_step_config:<tool_id>` onto `ctx.data` for the wrapper's duration (§6.2) and pops it after.
- Composite `reads`/`writes`/`reads_optional` equal the hand-written runbook's (built via the same `chain`/`parallel` helpers).

**Both**
- `python -m py_compile app/pipeline/spec/validator.py app/pipeline/spec/compiler.py` clean.
- `pytest tests/unit/pipeline/test_spec_validator.py tests/unit/pipeline/test_spec_compiler.py` green.
- This slice adds the `validate_spec`/`compile_spec`/`ValidationReport`/`ValidationError` re-exports to the existing `app/pipeline/spec/__init__.py` (created by doc 03), and makes the **three surgical wrapper edits** in `services/steps.py` that let proposable config actually flow (§6.2: `rank_external_references:138`, `rank_own_posts:214`, `fetch_search_references:86` — each gains a `_cfg(...)`-with-default read; behavior unchanged when no config is present). No change to `flow.py`, `artifacts.py`, `context.py`, or any file under `app/pipeline/tools/**` (the ACT-tail `ArtifactKey` additions are doc 06; the catalog is doc 03).
- The §3.3 adapter helpers are the only place that names sibling-doc fields, so a field rename in doc 03/04 is a ~8-line change here.

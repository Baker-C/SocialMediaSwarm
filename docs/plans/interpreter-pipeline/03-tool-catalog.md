# Task 03 — Tool Catalog (introspection)

> **Status:** Ready to implement. Authored cold from a verified read of the live tool modules + wiring layer.
> **Scope:** Backend only. ONE new module — `app/pipeline/spec/catalog.py` — plus a Pydantic `ToolCatalogDocument` model, a `ToolCatalog` wrapper class (the lookup object docs 05/10 consume), and a unit test. No tool code is touched. No spec execution is wired here (the compiler is doc 05; the ACT-tail tools are doc 06).
> **Target project:** `SocialMediaAutonomousAgents/backend/`.
>
> **Sibling-doc numbering (canonical, by filename — use these, ignore any stale numbers in older drafts):** spec model = **doc 04** (`PipelineSpecDocument`/`StepSpec`/`CompositeSpec`/`default_pipeline_spec`); validator + compiler = **doc 05**; ACT-tail tools (`compose_until_safe`/`publish_post`) = **doc 06**; attribution (adds `run_id`/`pipeline_hash`) = **doc 02**; agent-builder backend = **doc 10**; frontend = **doc 11**.

This doc builds the **read-only mirror** of the tool layer that the builder/validator/self-rewrite logic consults to know *what tools exist and what an LLM may legally wire into a spec*. It is the source of truth for the **CRUCIAL & HONEST split**: which `run()` kwargs are live engine-injected service objects (NOT proposable) versus which are LLM-tunable config (proposable into a `PipelineSpecDocument`).

---

## 1. Why this exists

A `PipelineSpecDocument` (doc 04) is editable DATA: an ordered list of `{tool_id, config}` entries plus the coarse ACT tools. Before the builder (doc 10) can propose a spec, and before the compiler (doc 05) can turn a spec into runnable `Step`s, **something must answer three questions for every tool**:

1. **What is this tool?** — its `TOOL_ID`, kind, purpose, and the artifact it writes (its `OUTPUT_MODEL`).
2. **What does its `run()` take?** — the full keyword signature, via `inspect.signature`.
3. **Of those kwargs, which are proposable config and which are engine-injected live services?** — the line an LLM must never cross.

> **What the catalog does NOT own: per-step artifact `reads`/`writes`.** A tool's read/write set is **not** a fixed property of the tool — it depends on how the *step* wires it. Verified: the SAME tool `deterministic.reference_rank` is used by `rank_external_references` (reads `TIMELINE_REFERENCES`, writes `TIMELINE_RANKED`) AND `rank_own_posts` (reads `OWN_POSTS`, writes `OWN_POSTS_RANKED`) — same tool, different I/O, selected at runtime by the `store_key` config (`reference_rank.py:36` `artifact_key_for_ctx_key(store_key)`). So the artifact-dependency graph the validator (doc 05) walks comes from each **`StepSpec.reads`/`StepSpec.writes`** (declared on the spec node — doc 04 stores them, copied from the runbook `Step.reads`/`Step.writes`), **NOT** from the catalog. The catalog's job for writes is only the *fixed-writes assertion*: see §3 and §5.2.

Today there is **no registry**. `app/pipeline/tools/__init__.py` is a one-line docstring (verified). The `TOOL_*` module constants exist purely as documentation and are read by nobody — confirmed by the grounding note *"TOOL_* module constants … are not used by the engine"*. The wiring that actually calls each tool lives in `app/pipeline/services/steps.py`, where every config value (`top_n=10`, `max_results_per_query=50`, `store_key="timeline_ranked"`, `source="timeline"`) is **hardcoded in a wrapper**. The catalog's job is to surface those tools as inspectable data without changing that.

**Non-goal:** the catalog does NOT make config actually flow from a spec into a tool. That requires editing the `steps.py` wrappers so they read config from the compiled step instead of hardcoding it — that is the **compiler's** job (**doc 05 §6.2**, config-binding "option A": each wrapper grows a `config: dict` kwarg and reads e.g. `config.get("top_n", MIN_TOP_N)`). This doc only *describes* what is wireable; doc 05 *honors* it. We state this boundary plainly in §6.

---

## 2. The load-bearing truth this doc must respect

Verified by reading the six live tool modules and running `inspect.signature` on each `run()` (`backend/app/pipeline/tools/**`). Three facts shape every design choice below.

### 2.1 Annotations are STRINGS, not types
Every tool module begins with `from __future__ import annotations`, so `inspect.signature(run).parameters[x].annotation` returns a **string** (`'TickDataService'`, `'str | None'`, `'list[dict[str, Any]]'`) — never a class object. The catalog therefore classifies parameters **by name and by annotation string**, and never by `isinstance`/type identity. Attempting `get_type_hints()` to resolve real types would import + evaluate every annotation (and pull `GatheredTweet`, `TickDataService`, etc. into a resolution context) for zero benefit — the string is sufficient and safer. **Decision: keep annotations as raw strings.** (See Decision Defense.)

### 2.2 "Required" does NOT mean "config"
The injected live services are keyword-only params with **no default** (`tick_data`, `post_registry`). But several genuine *config* params are ALSO keyword-only with no default (`queries`, `source`, `niche`, `top_posts`, `winner`). So requiredness cannot classify a param. The ONLY reliable signal is the **parameter name** matching a known, closed set of engine-injected dependency names. The catalog hard-codes that set (§4.3) and treats everything else as config.

### 2.3 Config is currently hardcoded in `steps.py`, not passed from data
`steps.py` proves the proposable surface is real but *unused today*: e.g. `reference_rank.run(ctx, rows=pool, top_n=MIN_TOP_N, store_key=ArtifactKey.TIMELINE_RANKED.value)` (steps.py:135-140). `top_n` and `store_key` ARE config the LLM *could* tune — but the wrapper pins them. **Verified: `top_n=MIN_TOP_N` is hardcoded at TWO call sites** — `rank_external_references` (steps.py:138) *and* `rank_own_posts` (steps.py:214) — both calling the SAME tool `deterministic.reference_rank`. The catalog reports `top_n` as `config`/`literal`; doc 05's compiler decides which a spec may override and (per doc 09's deterministic `top_n` proposer) tunes the per-step config, NOT the tool — so both ranker steps are independently tunable because config lives on the `StepSpec`, not the shared tool. We are honest in §6 that, **at the moment this catalog ships, no spec config reaches any tool** — the catalog is descriptive groundwork.

---

## 3. Verified inventory of the six tools

Read directly from the modules (paths under `backend/app/pipeline/tools/`). This table is the ground truth the introspector must reproduce. Note the **inconsistent constant sets** — the introspector must tolerate missing constants.

| Module (file) | `TOOL_ID` | `TOOL_KIND` | `TOOL_PURPOSE` | `OUTPUT_MODEL` | `TOOL_WRITES` | `TOOL_SOURCE` | `PROMPT_STEM` |
|---|---|---|---|---|---|---|---|
| `data/account_profile.py` | `data.account_profile` | `data` | ✅ (ln 15) | `AccountBundle` | `(ACCOUNT_BUNDLE,)` | `x_api` | — |
| `data/search_fetch.py` | `data.search_fetch` | `data` | ✅ (ln 15) | `SearchReferencesPayload` | `(SEARCH_REFERENCES,)` | `x_search` | — |
| `data/own_posts_fetch.py` | `data.own_posts_fetch` | `data` | ✅ (ln 15) | `OwnPostsPayload` | `(OWN_POSTS,)` | `ravendb` | — |
| `deterministic/reference_rank.py` | `deterministic.reference_rank` | `deterministic` | ✅ (ln 19) | `RankedReferencesPayload` | — *(absent)* | — | — |
| `llm/reference_pattern_summary.py` | `llm.reference_pattern_summary` | `llm` | ✅ (ln 16) | `ReferencePatternBrief` | — *(absent)* | — | `reference_pattern_summary` |
| `llm/compose_timeline_post.py` | `llm.compose_timeline_post` | `llm` | ✅ (ln 12) | — *(absent)* | — | — | `compose_timeline_post` |

> **`TOOL_PURPOSE` is present on ALL SIX modules** (verified line numbers above). `§4.2` reads it via `getattr(m, "TOOL_PURPOSE", "")`; the default is a safety net, not a regular path — every listed tool supplies it.

Also present but **NOT a runbook step tool**: `deterministic/reference_score.py` (`TOOL_ID = deterministic.reference_score`). It *does* define `run(ctx, *, metrics: dict) -> StepResult` (verified), but it is a **pure scalar helper that writes no artifact** (`return StepResult(ok=True, payload={"score": ...})` — no `ctx.set_artifact`, no `OUTPUT_MODEL`). It is never placed in a runbook and is not something a spec wires. The catalog excludes it the only honest way: **by omission from the explicit `_TOOL_MODULES` list (§4.1)** — NOT by a signature heuristic (its signature looks like a normal tool). Do not rely on "has a `ctx`-first `run`" to filter it; that test would wrongly include it.

**Crucial irregularities the introspector must survive (all verified):**
- `reference_rank` and `reference_pattern_summary` define **no `TOOL_WRITES`**. They write whichever artifact `store_key` resolves to at runtime (`artifact_key_for_ctx_key(store_key)`), so a static `TOOL_WRITES` would be a lie. `OUTPUT_MODEL` is still meaningful (the *shape* written), so the catalog reports `output_model` from `OUTPUT_MODEL` and reports `writes` as **dynamic/unknown** when `TOOL_WRITES` is absent.
- `compose_timeline_post` has **no `OUTPUT_MODEL` and no `TOOL_WRITES`**: it does `ctx.set("composed_body", body)` (a raw string under a non-artifact key), not `ctx.set_artifact(...)`. The catalog reports `output_model=None`, `writes=None`. This tool is the leaf the coarse `compose_until_safe` ACT tool (doc 06) will wrap; its catalog entry is informational only.
- `TOOL_SOURCE` exists on the three `data` tools only; `PROMPT_STEM` on the two `llm` tools only. Both are optional metadata in the document.

### 3.1 Verified `run()` signatures (the proposable surface)
From `inspect.signature` on each `run`. `ctx` is always `POSITIONAL_OR_KEYWORD`; everything else is `KEYWORD_ONLY`. Legend: **[I]** = engine-injected dep (NOT proposable), **[C]** = LLM-tunable config (proposable), **[ctx]** = the run context (never proposable, never injected as a dep — it is the carrier).

| Tool | Parameters (name : annotation-string : default) |
|---|---|
| `data.account_profile` | `ctx`[ctx] · `tick_data: TickDataService`[I] (required) · `account_id: str \| None = None`[C] |
| `data.search_fetch` | `ctx`[ctx] · `tick_data: TickDataService`[I] (required) · `queries: list[str]`[C] (required) · `authenticated_user_id: str \| None = None`[C] · `account_id: str \| None = None`[C] · `slot: str \| None = None`[C] · `max_results_per_query: int \| None = None`[C] |
| `data.own_posts_fetch` | `ctx`[ctx] · `post_registry: TrackedPostRepository`[I] (required) · `account_id: str \| None = None`[C] |
| `deterministic.reference_rank` | `ctx`[ctx] · `rows: list[dict[str, Any]]`[C] (required) · `top_n: int = 10`[C] · `exclude_ids: frozenset[str] \| None = None`[C] · `store_key: str = "ranked_references"`[C] |
| `llm.reference_pattern_summary` | `ctx`[ctx] · `source: SourceLabel`[C] (required) · `niche: str`[C] (required) · `top_posts: list[dict[str, Any]]`[C] (required) · `features: dict[str, Any] \| None = None`[C] · `store_key: str \| None = None`[C] |
| `llm.compose_timeline_post` | `ctx`[ctx] · `winner: GatheredTweet`[C] (required) · `niche: str`[C] (required) · `account_posting_prompt: str = ""`[C] · `account_personality: str = ""`[C] · `contrast_patterns: list \| None = None`[C] · `punctuation_rules: list \| None = None`[C] · `reference_context_block: str = ""`[C] · `regeneration_round: int = 0`[C] · `safety_reject_reason: str \| None = None`[C] |

> **Honest caveat baked into the model (§5):** params marked **[C]** are *signature-level* config — they are what the tool's `run()` will accept. That is NOT the same as *spec-proposable*. Many [C] params (e.g. `rows`, `top_posts`, `winner`, `exclude_ids`) are **derived artifacts wired by `steps.py` from upstream context**, not literals an LLM types into a spec. The catalog distinguishes these with a `config_origin` field per parameter (§4.4): `"literal"` (an LLM may set a JSON scalar/list), `"wired"` (the wrapper supplies it from context/artifacts — an LLM may NOT set it), or `"runtime"` (engine supplies from the tick, e.g. `account_id`, `slot`). This is the difference between "the function accepts it" and "you may put it in the spec."

---

## 4. File-by-file plan

| File | CHANGED / NEW / REUSED | One-line role |
|---|---|---|
| `app/pipeline/spec/__init__.py` | **NEW** | Package marker for the `app/pipeline/spec/` subsystem (this catalog + doc 05's `validator.py`/`compiler.py` live here). One-line docstring. **CC-13: this slice (doc 03, first in the §4 order) CREATES this marker; docs 04/05/06 treat it as REUSED — they do not re-create it.** (Verified absent today: `app/pipeline/spec/` does not exist in the live tree.) |
| `app/pipeline/spec/catalog.py` | **NEW** | Introspect every tool module → a `ToolCatalogDocument` per tool; expose `build_tool_catalog()`, `get_tool()`, `tool_catalog_hash()`, the `ToolCatalog` lookup class + `get_tool_catalog()` (the object docs 05/10 consume). |
| `app/models/tool_catalog.py` | **NEW** | Pydantic `ToolCatalogDocument` + `ToolParameter` + `ConfigField` models (the typed shape of one catalog entry + its proposable-config schema). |
| `app/pipeline/tools/__init__.py` | **REUSED** (read-only) | Already exists; the catalog imports the six tool modules via the static list in §4.1 — it does NOT scan the filesystem. |
| `app/pipeline/types/artifacts.py` | **REUSED** | `ArtifactKey`, `ARTIFACTS`, and each `OUTPUT_MODEL` Pydantic class are read for `output_model` naming + schema. |
| `app/services/voice_version_service.py` | **REUSED** (pattern only) | `compute_voice_hash` is the canonical-JSON-SHA256 recipe `tool_catalog_hash()` mirrors. Not imported; copied recipe. |
| `tests/unit/test_tool_catalog.py` | **NEW** | Assert all six tools appear, the injected/config split is correct, dynamic-writes tools report `writes=None`, and the hash is stable. |

### 4.1 Tool discovery: an explicit list, not a filesystem scan

**Decision: hardcode the module list; do not auto-discover by walking `tools/`.** (See Decision Defense.) `catalog.py` holds:

```python
# app/pipeline/spec/catalog.py
import hashlib
import inspect
import json
from typing import Callable

from app.models.tool_catalog import ConfigField, ToolCatalogDocument, ToolParameter
from app.pipeline.tools.data import account_profile, own_posts_fetch, search_fetch
from app.pipeline.tools.deterministic import reference_rank
from app.pipeline.tools.llm import compose_timeline_post, reference_pattern_summary

# Order is the catalog's canonical order (stable hash input).
_TOOL_MODULES = (
    account_profile,
    search_fetch,
    own_posts_fetch,
    reference_rank,
    reference_pattern_summary,
    compose_timeline_post,
)
```

`reference_score` is deliberately absent — it is a scalar helper that writes no artifact and is never a runbook step (§3), even though it happens to have a tool-shaped `run`. Exclusion is by omission from this list, not by a heuristic. The list is the single place a new tool gets registered, which is exactly the surgical, no-magic posture CLAUDE.md asks for.

> **`_internal.*` sentinels are NOT catalog tools (CC-8).** Doc 04's seed maps `collect_external_references` to the sentinel `tool_id="_internal.collect_external"` (a pure dict-promotion wrapper, `steps.py:90-114`, that calls no `tools/**` `run()`). The catalog deliberately does **not** include it: it is an interpreter primitive, not a wireable tool. Consequence the implementer must know: `"_internal.collect_external" in get_tool_catalog()` is `False`, so doc 05's validator R1 (`unknown_tool`) and compiler would reject the seeded baseline unless they recognize the `_internal.` prefix. **CC-8 resolution (owned by doc 05, NOT this doc):** doc 05 holds the closed set **`INTERNAL_PRIMITIVES`** (`= frozenset({"_internal.collect_external"})`) and a `_is_internal(tool_id)` prefix helper. The validator **skips the catalog-membership / reads-closure checks for `_internal.*`** and sources those leaves' reads/writes from the **spec node** (`StepSpec.reads`/`StepSpec.writes`); the compiler binds `_internal.collect_external` → `steps.collect_external_references` directly (not via the catalog). This catalog stays honest (six real tools); all sentinel handling lives in doc 05 where compile/validate live. (`run_for("_internal.collect_external")` is therefore not defined in `_TOOL_RUN` — `_internal.*` is never resolved through the catalog.)

### 4.2 Per-module introspection

For each module `m` in `_TOOL_MODULES`:

```python
def _introspect(m) -> ToolCatalogDocument:
    run = getattr(m, "run", None)
    if not callable(run):
        raise ValueError(f"Catalog module {m.__name__} has no run()")
    sig = inspect.signature(run)
    params = list(sig.parameters.values())
    if not params or params[0].name != "ctx":   # sanity assertion, not a filter:
        raise ValueError(f"{m.__name__}.run must take ctx first")  # every listed tool already does

    tool_id = getattr(m, "TOOL_ID", m.__name__)
    kind = getattr(m, "TOOL_KIND", "")
    purpose = getattr(m, "TOOL_PURPOSE", "")
    source = getattr(m, "TOOL_SOURCE", None)
    prompt_stem = getattr(m, "PROMPT_STEM", None)

    output_model = getattr(m, "OUTPUT_MODEL", None)
    output_model_name = output_model.__name__ if output_model is not None else None

    writes_const = getattr(m, "TOOL_WRITES", None)            # tuple[ArtifactKey] | None
    writes = [k.value for k in writes_const] if writes_const else None  # None ⇒ dynamic (store_key)

    reads_const = getattr(m, "TOOL_READS", None)              # tuple[ArtifactKey] | None — only ACT tools (doc 06)
    reads = [k.value for k in reads_const] if reads_const is not None else None  # None ⇒ dynamic (§4.3b)

    # Skip ctx (always first) AND a literal `deps` param: the doc-06 ACT tools take
    # run(ctx, deps) and read everything off deps — `deps` is the engine handle, never
    # a kwarg. The SENSE tools have no `deps` param (their wrappers spread deps fields),
    # so this skip is a no-op for them and correctly empties the ACT tools' surface.
    rest = [p for p in params[1:] if p.name != "deps"]
    parameters = [_introspect_param(p) for p in rest]
    return ToolCatalogDocument(
        tool_id=tool_id, kind=kind, purpose=purpose, source=source,
        prompt_stem=prompt_stem, output_model=output_model_name,
        writes=writes, reads=reads, parameters=parameters,
    )
```

`_introspect_param` (§4.4) builds one `ToolParameter` per kwarg. `reads` is resolved in §4.3b. **CC-2 (canonical): there is NO `invariant_tool` field and NO `TOOL_INVARIANT` module constant.** The structure a valid spec must have (a guardian-bearing step and a terminal publish step) is detected by doc 05's validator **purely from artifacts** — R7 checks that some catalog tool's static `writes` includes `safety_verdict` and that the terminal `PUBLISHED_POST` writer's catalog `writes` statically includes `published_post`. No tool module declares an invariant flag; the catalog never reads or stores one.

### 4.3 The engine-injected dependency set (the honest line)

A closed, hand-maintained set keyed by **parameter name**. The first five names are verified against the live `PostRunDeps` dataclass (deps.py:14-22 — `tick_data`, `repo`, `post_registry`, `pulled_tweets`, `twitter`) and every `steps.py` call site. The sixth (`guardian`) is **NOT on today's `PostRunDeps`**; it is added by doc 06's `PostRunDeps` extension (`deps.py` gains `guardian`, `max_regeneration_rounds`, `bypass_post_cooldown`, `live: ActLive`). We list it now because the set is the one place that knowledge lives — be honest that it is forward-looking, not present in the current dataclass.

```python
# Parameter NAME -> the live dep it is injected from.
# These are NEVER proposable; the engine wires them around every leaf.
ENGINE_INJECTED_DEPS: dict[str, str] = {
    # ── present on PostRunDeps today (deps.py:18-22) ──
    "tick_data": "PostRunDeps.tick_data",        # TickDataService (composite)
    "repo": "PostRunDeps.repo",                  # AccountRepository
    "post_registry": "PostRunDeps.post_registry",# TrackedPostRepository | None
    "pulled_tweets": "PostRunDeps.pulled_tweets",# PulledTweetRepository | None
    "twitter": "PostRunDeps.twitter",            # TwitterService | None
    # ── added by doc 06's PostRunDeps extension (NOT on today's dataclass) ──
    "guardian": "PostRunDeps.guardian",          # SafetyGuardian — arrives via deps.guardian (doc 06)
}
```

> `guardian` is listed even though no *current* tool takes it and it is not yet a `PostRunDeps` field: the coarse `compose_until_safe` / `publish_post` tools from doc 06 read it as `deps.guardian` (see §4.3a for why the ACT tools are special). A name appearing here is injected; period. (The cost ceiling + safety guardian are NON-BYPASSABLE invariants the engine wraps around leaves — they are never expressible as config, which is exactly why `guardian` lives in the injected set and never in `config`.)

### 4.3a The ACT-tail tools take only `(ctx, deps)` — zero proposable config (HONEST)

The six tools introspected above are the SENSE tools, whose `run()` spreads many kwargs (`tick_data`, `rows`, `top_n`, …) that the catalog classifies. **The doc-06 ACT tools are structurally different and the catalog must say so plainly:**

- `compose_until_safe.run(ctx, deps)` and `publish_post.run(ctx, deps)` take **exactly two params** — `ctx` and `deps` — and read *everything* (account, ranked refs, guardian, run_id) off `deps.live` / `deps.guardian` (verified doc 06 §5.1/§5.2). They expose **NO per-kwarg config** and have **NO `inspect.signature`-visible proposable params**.
- Therefore, for these two tools, `parameters` is effectively `[]` after `ctx`/`deps` are skipped, and **`proposable_params == []`**. They are wired into a spec by *tool-selection + ordering* only — never by config. A spec author tunes the compose loop's breadth via `max_regeneration_rounds`, which is an **engine-injected dep** (doc 06), NOT a tool kwarg, so it is non-proposable too.
- The four "soul-derived compose fields" (`account_posting_prompt`, `account_personality`, `contrast_patterns`, `punctuation_rules`) appear on the **legacy `llm.compose_timeline_post`** leaf, which `compose_until_safe` *wraps internally* (doc 06 calls `compose_formatted_post` directly, binding those fields from `account.*`). `compose_timeline_post` is in the catalog for **informational** purposes only (§3) and is **not a spec-wired tool** — so those four fields are never actually spec-proposable in practice. §4.4's classification of them as `literal` describes the legacy leaf's *signature surface*, not a knob any real spec sets. The validator (doc 05) only ever sees `compose_until_safe`, which has no config.

**Net for the implementer:** the catalog introspects the ACT tools the same mechanical way (read `run` params, skip `ctx` and `deps`), yielding an entry with `parameters=[]`, `proposable_params=[]`, `writes` from `TOOL_WRITES`, `reads` from `TOOL_READS`. No special-casing of the ACT tools' *classification* is needed; the honesty is that they contribute zero proposable surface. Their `TOOL_WRITES` — `(COMPOSED_POST, SAFETY_VERDICT)` for `compose_until_safe` and `(PUBLISHED_POST,)` for `publish_post` — are fixed, so `writes` is concrete, not `None`. **CC-2: there is no `invariant_tool` flag.** Doc 05's R7 requires these two tools *by their static catalog `writes`* — a leaf whose catalog `writes` includes `safety_verdict` (the guardian-bearing `compose_until_safe`) must exist, and the terminal `PUBLISHED_POST` writer's catalog `writes` must statically include `published_post` (the idempotent `publish_post`). The artifacts ARE the signal; no separate marker is stored.

### 4.3b The catalog's `reads`/`writes` fields — fixed-only, honest `None` when dynamic

Doc 05's validator (R3 dangling-read, R4 cycle, R6 terminal-publish) and its compiler (`leaf reads=tuple(tool.reads)`) read `reads`/`writes` from the catalog entry. As established in §1, a tool's reads/writes are **per-step, not per-tool**, for the dynamic ranker/brief tools. So the catalog reports:

- **`writes`**: from `TOOL_WRITES` when the module declares it (the three data tools + the two ACT tools have fixed writes); **`None`** for `reference_rank` / `reference_pattern_summary`, whose write target is chosen at runtime via `store_key` (§3). `None` honestly means "dynamic — the *step* decides".
- **`reads`**: there is **no `TOOL_READS` constant on any of the six SENSE modules** (verified). The only tools with a *fixed* read contract are the doc-06 ACT tools (each declares a `TOOL_READS` constant). **Canonical read sets (doc 06 §7.1, authoritative — match these exactly):** `compose_until_safe` declares `TOOL_READS = (TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS, TIMELINE_RANKED)` — it builds `ranked_refs` from the `TIMELINE_RANKED` artifact, so that is a real upstream read; its live `AccountDocument`/`guardian` inputs arrive via `deps.live` and are NOT artifacts. `publish_post` declares `TOOL_READS = (COMPOSED_POST, SAFETY_VERDICT)`. For the six SENSE tools `reads` is **`None`** (dynamic — the step's `store_key`/wiring determines what it reads). So `_introspect` does: `reads_const = getattr(m, "TOOL_READS", None); reads = [k.value for k in reads_const] if reads_const is not None else None`.

**The graph is validated from the SPEC NODE, not the catalog (the single authoritative answer to the cross-doc "spec node vs catalog" ambiguity):** doc 05's R3/R4 walk `StepSpec.reads`/`StepSpec.writes` (doc 04 stores them per node, copied from the runbook). The catalog's `reads`/`writes` are used by doc 05 for **one** thing — the *fixed-writes / fixed-reads assertion*: when a tool has a non-`None` catalog `writes`/`reads`, the spec node's declared writes/reads MUST match it (a fixed-contract tool cannot be re-wired); when the catalog field is `None`, the tool is dynamic and the node's declaration is taken as-is (constrained only to be a valid `ArtifactKey`). This keeps the dependency graph driven by the editable spec while still letting the catalog catch a spec that lies about a fixed tool's I/O. R6's terminal-`PUBLISHED_POST` check resolves cleanly because `publish_post`'s catalog `writes` is the fixed `(PUBLISHED_POST,)`.

### 4.4 Per-parameter classification → `ToolParameter`

```python
# Names the ENGINE supplies from the live tick, not from a spec literal and not a dep object.
RUNTIME_SUPPLIED: frozenset[str] = frozenset({"account_id", "slot", "niche"})

# Names the WRAPPER derives from upstream artifacts/context (an LLM may NOT set these).
WIRED_FROM_CONTEXT: frozenset[str] = frozenset({
    "rows", "top_posts", "winner", "queries", "features",
    "authenticated_user_id", "exclude_ids", "store_key", "source",
    "reference_context_block", "regeneration_round", "safety_reject_reason",
})

def _introspect_param(p) -> ToolParameter:
    name = p.name
    annotation = "" if p.annotation is inspect._empty else str(p.annotation)
    required = p.default is inspect._empty
    default = None if p.default is inspect._empty else p.default

    if name in ENGINE_INJECTED_DEPS:
        kind = "injected"; origin = "injected"
    elif name in RUNTIME_SUPPLIED:
        kind = "config";   origin = "runtime"
    elif name in WIRED_FROM_CONTEXT:
        kind = "config";   origin = "wired"
    else:
        kind = "config";   origin = "literal"   # the genuinely LLM-tunable scalars

    return ToolParameter(
        name=name, annotation=annotation, required=required,
        default=_json_safe(default), kind=kind, config_origin=origin,
    )
```

`_json_safe` coerces defaults to JSON-storable values (`frozenset()` → `[]`, callables → their `__name__`); in practice every tool default is already a JSON scalar/`None` (verified — `10`, `0`, `""`, `None`, `"ranked_references"`).

**The result of this classification on the live tools** (the honest answer to "what can the LLM wire?"):

| Parameter | Appears in | `kind` | `config_origin` | LLM-proposable? |
|---|---|---|---|---|
| `tick_data`, `post_registry` | data tools | `injected` | `injected` | **No** — live service object |
| `account_id`, `slot` | several | `config` | `runtime` | **No** — engine supplies from tick |
| `niche` | rank-summary, compose | `config` | `runtime` | **No** — from `ctx.niche` |
| `rows`, `top_posts`, `winner` | rank, summary, compose | `config` | `wired` | **No** — derived artifact |
| `queries`, `features`, `exclude_ids`, `store_key`, `source` | data/det/llm | `config` | `wired` | **No** — wrapper-computed |
| `authenticated_user_id` | search | `config` | `wired` | **No** — from bundle |
| `reference_context_block`, `regeneration_round`, `safety_reject_reason` | compose | `config` | `wired` | **No** — compose-loop state |
| `top_n` | reference_rank | `config` | `literal` | **Yes** — an int |
| `max_results_per_query` | search_fetch | `config` | `literal` | **Yes** — an int |
| `account_posting_prompt`, `account_personality`, `contrast_patterns`, `punctuation_rules` | `compose_timeline_post` (legacy leaf) | `config` | `literal` | **Signature-only** — on the legacy `compose_timeline_post` leaf, which the ACT tool `compose_until_safe` wraps and binds from `account.*`; that leaf is informational-only in the catalog and is never spec-wired (§4.3a), so these are not live spec knobs |

So the **truly free knobs an LLM may put in a spec today are exactly two integers** — `top_n` and `max_results_per_query`. The four soul-derived compose fields are `literal` only on the legacy `compose_timeline_post` *signature*, which is informational in the catalog and never spec-wired (the ACT tool `compose_until_safe` binds them from `account.*`, §4.3a) — so in practice they are not reachable knobs either. **Everything else is either a live dependency, a tick-runtime value, or a wired artifact.** The catalog says this plainly via `config_origin`, and the validator (doc 05) rejects any spec that tries to set a non-`literal` parameter. This is the whole point of being honest: the "data pipeline" is wireable at the *tool-selection + ordering* grain and a *very thin* config grain — not "the LLM rewrites every argument."

---

## 5. The `ToolCatalogDocument` model (`app/models/tool_catalog.py`)

Mirrors the soul-versioning model style (Pydantic, explicit fields, JSON-dumpable). NOT a RavenDB document — the catalog is derived from code at process start, never persisted as a source of truth (it would drift). It IS hashed (§5.1) so a spec can record which catalog version it was validated against.

```python
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

ParamKind = Literal["injected", "config"]
ConfigOrigin = Literal["injected", "runtime", "wired", "literal"]
# The closed type vocabulary doc 05's _typecheck switches on (validator §5.1).
ConfigType = Literal["str", "int", "float", "bool", "list[str]", "dict"]

class ToolParameter(BaseModel):
    name: str
    annotation: str = ""               # raw annotation STRING (see §2.1)
    required: bool = False
    default: Any = None                # JSON-safe default, or None
    kind: ParamKind                    # injected => live service; config => everything else
    config_origin: ConfigOrigin        # only config_origin == "literal" is spec-proposable

class ConfigField(BaseModel):
    """The typed schema entry doc 05's validator type-checks a spec config value
    against. Derived from a proposable (literal) ToolParameter — see config_schema."""
    name: str
    type: ConfigType
    required: bool = False

class ToolCatalogDocument(BaseModel):
    tool_id: str
    kind: str = ""                     # data | deterministic | llm
    purpose: str = ""
    source: str | None = None          # TOOL_SOURCE (data tools only)
    prompt_stem: str | None = None     # PROMPT_STEM (llm tools only)
    output_model: str | None = None    # OUTPUT_MODEL.__name__ or None (compose => None)
    reads: list[str] | None = None     # fixed reads (ACT tools), or None when dynamic (§4.3b)
    writes: list[str] | None = None    # fixed writes, or None when dynamic (store_key) (§4.3b)
    parameters: list[ToolParameter] = Field(default_factory=list)
    # CC-2: NO invariant_tool field. Doc 05's R7 detects the guardian/publish invariants
    # from the static `writes` artifacts (writes ⊇ safety_verdict / published_post), not a flag.

    @property
    def injected_params(self) -> list[ToolParameter]:
        return [p for p in self.parameters if p.kind == "injected"]

    @property
    def proposable_params(self) -> list[ToolParameter]:
        return [p for p in self.parameters if p.config_origin == "literal"]

    @property
    def config_schema(self) -> list[ConfigField]:
        """The proposable surface as a TYPED schema (the `catalog.get(id).config_schema`
        doc 05's R2 type-checks against). One ConfigField per literal-origin param,
        with its JSON type derived from the annotation string (§5.2)."""
        return [
            ConfigField(name=p.name, type=_config_type(p.annotation), required=p.required)
            for p in self.proposable_params
        ]
```

### 5.2 Annotation-string → `ConfigType` (`_config_type`)

`config_schema` needs a JSON type per proposable param, but annotations are raw strings (§2.1). A tiny, closed mapping — anything unrecognized falls back to `"str"` and is flagged in the test, never silently mistyped:

```python
def _config_type(annotation: str) -> ConfigType:
    a = annotation.replace(" ", "")
    if a.startswith("int") or a == "int|None":            return "int"
    if a.startswith("float") or a == "float|None":        return "float"
    if a.startswith("bool"):                              return "bool"
    if a.startswith("list[str]") or a == "list[str]|None": return "list[str]"
    if a.startswith("list") or a.startswith("dict"):      return "dict"  # coarse; no list-of-scalar knob exists today
    return "str"
```

On the live proposable set this yields exactly: `top_n → "int"`, `max_results_per_query → "int"` (annotation `int | None`), `account_posting_prompt`/`account_personality → "str"` (annotation `str`), and `contrast_patterns`/`punctuation_rules → "dict"` (annotation `list | None` — the coarse `list…→dict` fallback; these are legacy-leaf-only, never spec-reached per §4.3a, so the coarse type is harmless). That matches doc 05 §5.1's only-real-numeric-today expectation (`top_n: int`, the sole numeric a real spec can set).

`catalog.py` exposes:

```python
# CC-1: get_tool_catalog() (below) is the SINGLE factory for the catalog OBJECT. The two
# functions here are the internal list producer + the hash; they are NOT catalog-object
# factories. The name `build_catalog()` does not exist anywhere (CC-1). Consumers (docs
# 05/10) always go through get_tool_catalog() / catalog.get(id) / id in catalog — never the
# raw list. `build_tool_catalog()` is internal plumbing (ToolCatalog.__init__ + the hash use it).
def build_tool_catalog() -> list[ToolCatalogDocument]: ...   # INTERNAL: raw list, _TOOL_MODULES order
def get_tool(tool_id: str) -> ToolCatalogDocument | None: ...# convenience free fn (list-backed); object callers use catalog.get()
def tool_catalog_hash() -> str: ...                          # §5.1

# The wrapper that actually runs for each tool_id. Verified: every runbook leaf is a
# steps.py wrapper of shape (ctx, deps) -> StepResult, exactly one per tool_id today
# (load_account_bundle→data.account_profile, …; the two rankers share
# deterministic.reference_rank — the wrapper, not the tool, is keyed, so each step's
# wrapper is distinct). doc 05's compiler binds Step.run from THIS map, not from a
# (non-serializable) field on the hashable ToolCatalogDocument.
from app.pipeline.services import steps
_TOOL_RUN: dict[str, Callable] = {
    "data.account_profile":          steps.load_account_bundle,
    "data.search_fetch":             steps.fetch_search_references,
    "data.own_posts_fetch":          steps.fetch_own_post_history,
    "deterministic.reference_rank":  None,   # shared by 2 steps → resolved per-step by the compiler, not here
    "llm.reference_pattern_summary": None,   # shared by 2 steps → likewise
    "llm.compose_timeline_post":     None,   # informational only; never spec-wired (§4.3a)
    # doc 06 adds: "llm.compose_until_safe": steps.compose_step,
    #              "data.publish_post":      steps.publish_step,
}

class ToolCatalog:
    """The lookup OBJECT docs 05 (validator/compiler) and 10 (builder) consume.

    Docs 05/10 were authored against `catalog.get(tool_id)` / `tool_id in catalog`
    returning a single entry — NOT the raw list `build_tool_catalog()` returns. This
    thin wrapper IS that object; it is the resolution of the cross-doc 'no ToolCatalog
    class' seam (the validator's `catalog` arg type and the builder's `_load_catalog()`
    return type are both `ToolCatalog`).
    """
    def __init__(self, tools: list[ToolCatalogDocument] | None = None) -> None:
        self._by_id = {t.tool_id: t for t in (tools if tools is not None else build_tool_catalog())}

    def get(self, tool_id: str) -> ToolCatalogDocument | None:
        return self._by_id.get(tool_id)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._by_id

    def all(self) -> list[ToolCatalogDocument]:
        return list(self._by_id.values())   # _TOOL_MODULES order (dict preserves insertion)

    def run_for(self, tool_id: str) -> Callable | None:
        """The bound (ctx, deps) -> StepResult wrapper for a tool_id, or None when the
        tool is shared across steps (the compiler binds those per-step — see note below)."""
        return _TOOL_RUN.get(tool_id)

def get_tool_catalog() -> ToolCatalog:
    """Module-level default catalog object. Built fresh from code (cheap, pure).
    This is the symbol doc 05's compiler defaults its `catalog` arg to, and doc 10's
    builder `_load_catalog()` returns. `validate_spec(doc, get_tool_catalog())`."""
    return ToolCatalog()
```

> **Catalog-entry field contract for doc 05 (pinned — resolves the cross-doc `ToolDef` mismatch).** A `ToolCatalogDocument` returned by `ToolCatalog.get()` exposes exactly the members the validator/compiler read: `tool_id`, `kind`, `purpose`, `output_model`, `reads` (fixed or `None`), `writes` (fixed or `None`), `parameters`, the derived `config_schema` (§5) + `proposable_params`. **There is NO `invariant_tool` member (CC-2)** — doc 05's R7 derives the guardian/publish invariants from the static `writes` (`writes ⊇ ["safety_verdict"]` / terminal `writes ⊇ ["published_post"]`), so no flag is needed or stored. **There is no separate `ToolDef` type** — `ToolCatalogDocument` IS the catalog entry doc 05 calls `tool` in its `_tool(catalog, tool_id)` adapter; doc 05's §3.2 `ToolDef`/`ConfigField`/`ToolCatalog` shapes are satisfied by (and should be re-pointed to) these names. The one member doc 05 reads that is NOT a field on the hashable doc is the bound **`run` callable**: it cannot live on a Pydantic model that `model_dump(mode="json")`s into the hash (§5.1), so the `ToolCatalog` wrapper exposes it via `run_for(tool_id)`. For the two shared tools (`reference_rank`, `reference_pattern_summary`) `run_for` returns `None` and doc 05's compiler binds `Step.run` from its own per-step wrapper map (doc 05 §6.2 — the wrapper is what carries the resolved `store_key`); for the unique-wrapper tools and the doc-06 ACT tools `run_for` returns the wrapper directly. This keeps the hash pure and the binding unambiguous.

### 5.1 `tool_catalog_hash()` — mirror `compute_voice_hash`

So a `PipelineSpecDocument` can stamp the catalog version it validated against (parallel to how a `TrackedPost` stamps `voice_version_hash`). Reuse the **exact recipe** from `voice_version_service.compute_voice_hash` (canonical JSON, sorted keys, SHA256) — copy the recipe, do **not** import it (it is soul-specific):

```python
def tool_catalog_hash() -> str:
    payload = [d.model_dump(mode="json") for d in build_tool_catalog()]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

The hash changes whenever a tool's id, kind, output model, reads, writes, or any parameter (name/annotation/default/classification) changes — i.e. whenever the proposable surface or the fixed I/O contract changes. That is the property doc 05's validator needs.

> **Cross-ref:** doc 04 defines `PipelineSpecDocument`; if a "validated-against-catalog" stamp is wanted it carries a `tool_catalog_hash` field set at validate-time (optional — doc 04's model does not require it). Doc 05 (validator) consumes `ToolCatalog.get()` + `config_schema` + the static `writes`/`reads` (R7 reads `writes` to detect the guardian/publish invariants — CC-2, no flag) to reject illegal wirings; doc 10 (builder) consumes `proposable_params`. This doc only *produces* the catalog; it does not own those consumers.

---

## 6. What the LLM CAN and CANNOT wire (state plainly)

This section is the deliverable the orchestrator asked to be blunt about. After this catalog ships:

**CAN (today):**
- **Select** which catalog tools run and **in what order** (the spec is an ordered tool list — doc 04).
- **Set `literal`-origin config**: `top_n` (on EITHER ranker step — `rank_external_references` and `rank_own_posts` both wire `deterministic.reference_rank`, tuned independently per `StepSpec`), `max_results_per_query` (search_fetch). Two integer knobs.

**CANNOT (ever, by construction):**
- Touch any `injected` parameter (`tick_data`, `post_registry`, `repo`, `twitter`, `guardian`). These are live objects wired by the engine around every leaf; they are not serializable and not in the spec vocabulary. (`guardian` arrives via doc 06's `deps.guardian`.)
- Set `runtime` params (`account_id`, `slot`, `niche`) — the engine supplies them from the tick.
- Set `wired` params (`rows`, `top_posts`, `winner`, `queries`, `features`, `store_key`, `source`, `exclude_ids`, `authenticated_user_id`, and the compose-loop state fields) — these are derived from upstream artifacts/context by the `steps.py` wrapper, not literals.
- Configure the **ACT tools** (`compose_until_safe`, `publish_post`) at all — they take only `(ctx, deps)` and expose **zero** proposable params (§4.3a). A spec wires them by selection/ordering only.
- Touch the **four soul-derived compose fields** (`account_posting_prompt`, `account_personality`, `contrast_patterns`, `punctuation_rules`). They are signature params of the *legacy* `llm.compose_timeline_post` leaf, which `compose_until_safe` wraps and binds from `account.*`; that leaf is informational-only in the catalog and is never spec-wired, so these are not reachable knobs (§4.3a). (`config_origin="literal"` on them describes the legacy signature surface, not a live spec knob.)
- Remove the safety guardian or cost ceiling — non-bypassable engine invariants (doc 06/07), not catalog entries.
- Write a new tool. The builder only WIRES + CONFIGURES existing catalog tools (project constraint).

**Honest limitation of THIS doc:** the catalog is **descriptive**. It reports that `top_n` is a `literal` knob, but the live `reference_rank` wrapper still hardcodes `top_n=MIN_TOP_N` at BOTH ranker sites (steps.py:138 and steps.py:214). **No spec config reaches any tool until doc 05's compiler (§6.2, option A) rewrites the `steps.py` wrappers** to accept a `config: dict` kwarg and read from the compiled step. Until then, `config_origin="literal"` is a *promise about the surface*, redeemed by doc 05. We do not pretend otherwise.

---

## 7. Decision Defense

**Why classify by parameter NAME against a closed set, not by annotation type?**
Because annotations are strings (§2.1) and "required" is ambiguous (§2.2). The injected services are a small, stable, hand-known set (`PostRunDeps` has five fields; `guardian` is the sixth ACT-tail dep). A name-keyed set is the only signal that cleanly separates `tick_data` (injected) from `queries` (config) when both are required keyword-only params with string annotations. It is also auditable: one dict, one place, reviewed on every tool addition. The alternative — resolving real types via `get_type_hints` and checking `issubclass(t, (TickDataService, …))` — imports and evaluates every annotation, couples the catalog to concrete service classes, and still fails on `guardian` (no current tool references it). More code, more coupling, same answer.

**Why a hardcoded module list instead of `pkgutil.walk_packages(tools)`?**
Auto-discovery would (a) import `reference_score` and other non-step helpers and need a guard to reject them anyway, (b) make the catalog's canonical order (and thus its hash) depend on filesystem iteration order, and (c) hide tool registration behind import magic. An explicit six-line tuple is simpler, deterministic, and makes "add a tool" a visible one-line diff — exactly CLAUDE.md's surgical/no-speculative-abstraction posture. When the count is six, a loop is over-engineering.

**Why `config_origin` instead of a plain `proposable: bool`?**
A boolean would collapse three genuinely different "not a free literal" reasons (`injected` live object, `runtime` tick value, `wired` artifact) into one, losing the information the validator (doc 05) and the dashboard need to explain *why* a wiring was rejected ("that's a derived artifact, not a knob"). The four-value enum costs nothing and is the difference between an honest catalog and a misleading one. `proposable_params` (the boolean view) is still available as a derived property for callers that only want the free knobs.

**Why report `writes=None` for `reference_rank`/`reference_pattern_summary` instead of inferring from `store_key`?**
Their target artifact is chosen at runtime via `artifact_key_for_ctx_key(store_key)` — it is genuinely dynamic. Encoding a static guess (e.g. "writes TIMELINE_RANKED") would be wrong for the own-posts wiring of the same tool. `None` honestly says "dynamic; see the wiring." The spec node (`StepSpec.writes`, doc 04) carries the concrete write per step, and doc 05's validator/compiler use that for the dependency graph while using the catalog's `None` to mean "the node's declaration is authoritative here" (§4.3b).

**Why does the dependency graph come from the SPEC NODE's reads/writes, not the catalog's?**
Because reads/writes are a property of the *step's wiring*, not the tool: the same `deterministic.reference_rank` reads/writes different artifacts in `rank_external_references` vs `rank_own_posts` (selected by `store_key`). A per-tool catalog `reads`/`writes` literally cannot express that without one entry per wiring, which defeats "one tool, many uses." So the editable `StepSpec.reads`/`writes` (doc 04) is the graph source of truth, and the catalog's `reads`/`writes` are a narrower *fixed-contract assertion* (`None` = dynamic, defer to the node). This is the single answer to the cross-doc "spec node vs catalog" question and keeps the graph driven by the data a builder actually edits.

**Why add a `ToolCatalog` wrapper class on top of `build_tool_catalog()` -> list?**
The list is the right *producer* shape (ordered, hashable). But every consumer (doc 05 validator, doc 05 compiler, doc 10 builder) does point lookups by `tool_id` and membership tests, and was authored against `catalog.get(id)` / `id in catalog`. Returning a bare list would force each consumer to build its own `{t.tool_id: t}` index — three copies of the same dict, three places to drift. One tiny wrapper (built from the list, preserving order) gives them the exact interface they assume, plus `run_for` to bridge the one thing a hashable Pydantic doc can't hold (a live callable). It is the smallest change that makes docs 05/10 implementable as written.

**Why not persist the catalog as a RavenDB document?**
It is a pure function of the code. Persisting it invites drift (code says one thing, stored doc says another). We derive it at process start and *hash* it instead — the hash is the durable artifact a spec references, and it is always recomputable from code. This mirrors the soul pattern's spirit (versioned, hashable) without inventing a second source of truth for something the code already defines.

---

## 8. Definition of Done (this slice)

- `app/pipeline/spec/__init__.py` and `app/pipeline/spec/catalog.py` exist; `app/models/tool_catalog.py` defines `ToolParameter` + `ConfigField` + `ToolCatalogDocument`. `catalog.py` exposes `build_tool_catalog()`, `get_tool()`, `tool_catalog_hash()`, the `ToolCatalog` class, and `get_tool_catalog()`.
- `python -m py_compile` clean on the three new files.
- `build_tool_catalog()` returns **exactly six** `ToolCatalogDocument`s (no `reference_score`), in `_TOOL_MODULES` order.
- `get_tool_catalog()` returns a `ToolCatalog`; `cat.get("data.account_profile")` returns that entry, `"nope" in cat` is `False`, and `cat.all()` is the six entries in order. (This is the object docs 05/10 consume.)
- For `data.account_profile`: `injected_params` is `[tick_data]`; `account_id` is `config`/`runtime`; `reads is None`; `writes == ["account_bundle"]`. (`ToolCatalogDocument` has no `invariant_tool` field — CC-2.)
- For `deterministic.reference_rank`: `output_model == "RankedReferencesPayload"`, `reads is None`, `writes is None`, and `proposable_params` includes `top_n` (default `10`) and excludes `rows`/`store_key`/`exclude_ids`; `config_schema == [ConfigField(name="top_n", type="int", required=False)]`.
- For `llm.compose_timeline_post`: `output_model is None`, `reads is None`, and `writes is None`; `account_posting_prompt`/`contrast_patterns`/`punctuation_rules` are `config`/`literal` (legacy-signature surface, never spec-reached — §4.3a).
- **Forward contract for the doc-06 ACT tools (graded once doc 06 appends them to `_TOOL_MODULES`/`_TOOL_RUN`):** the SAME mechanical introspection (skip `ctx` + `deps`) must yield, for `llm.compose_until_safe`: `parameters == []`, `proposable_params == []`, `config_schema == []`, `reads == ["timeline_analysis", "own_posts_analysis", "timeline_ranked"]`, `writes == ["composed_post", "safety_verdict"]` (**concrete, not `None`**); and for `data.publish_post`: `parameters == []`, `proposable_params == []`, `config_schema == []`, `reads == ["composed_post", "safety_verdict"]`, `writes == ["published_post"]` (**concrete, not `None`**). These concrete `writes`/`reads` are exactly what doc 05's R7 keys on (CC-2: no `invariant_tool` flag). `run_for("llm.compose_until_safe") == steps.compose_step` and `run_for("data.publish_post") == steps.publish_step` after doc 06's `_TOOL_RUN` additions.
- No tool param is classified `config`/`literal` unless it is one of: `top_n`, `max_results_per_query`, or the four compose soul fields. (Guards the honest split.)
- `config_schema` is empty for every tool except `reference_rank` (`top_n`), `search_fetch` (`max_results_per_query`), and `compose_timeline_post` (the four legacy soul fields).
- `tool_catalog_hash()` is stable across two calls and changes if a tool param default is edited (tested by monkeypatching one module constant).
- `tests/unit/test_tool_catalog.py` asserts all of the above; `pytest tests/unit/test_tool_catalog.py` green.
- **No file under `app/pipeline/tools/` is modified.** (Catalog is read-only over the tool layer.) The `_TOOL_RUN` map imports `app.pipeline.services.steps` (read-only) to expose `run_for`; that import does not edit `steps.py`.

---

## 9. Cross-references (shared types owned elsewhere)

- **doc 04 — pipeline spec model + versioning:** owns `PipelineSpecDocument`/`StepSpec`/`CompositeSpec`. `StepSpec.reads`/`writes` are the dependency-graph source of truth (§4.3b); `StepSpec.config` holds only the `literal` knobs this catalog surfaces. May optionally add a `tool_catalog_hash` field stamped from §5.1.
- **doc 05 — validator + compiler:** consumes `ToolCatalog.get()` / `in`, `config_schema` (for R2 type-checks), `reads`/`writes` (R7 detects the guardian/publish invariants from the static `writes` — CC-2, no flag; the fixed-contract assertion uses both, §4.3b), and `run_for(tool_id)` to bind a leaf's `run`. This doc owns the rewrite of `steps.py` wrappers (config-binding option A, doc 05 §6.2) that redeems §6's "literal config flows" promise. The `_internal.*` sentinel handling (R1 membership skip, compiler binding) is owned by doc 05's `INTERNAL_PRIMITIVES` set (CC-8) — see §4.1.
- **doc 06 — ACT-tail tools:** adds `compose_until_safe` / `publish_post` (each `(ctx, deps)`-only, fixed `TOOL_READS`/`TOOL_WRITES`; **no `TOOL_INVARIANT` constant** — CC-2); adds `guardian`/`max_regeneration_rounds`/`live` to `PostRunDeps`; adds `compose_step`/`publish_step` wrappers. Their catalog entries appear once their modules are appended to `_TOOL_MODULES` and `_TOOL_RUN` (§4.1, §5). Their fixed `reads`/`writes` are what doc 05's R7 keys on.
- **doc 10 — agent-builder backend:** consumes `proposable_params` + `config_origin` (and `ToolCatalog` via `get_tool_catalog()`) to accept/reject proposed wirings; rejects any spec that sets a non-`literal` parameter.

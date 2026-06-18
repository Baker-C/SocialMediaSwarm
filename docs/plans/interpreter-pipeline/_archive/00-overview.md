# Interpreter Pipeline — Implementation Plan (Overview)

> **Status:** Authored + adversarially dry-run + reconciled. Pick up cold from this folder.
> **Architecture chosen:** **The Interpreter** — make each account's posting *pipeline* into editable **data**
> (a per-account `PipelineSpecDocument` in RavenDB) executed by ONE generic in-process interpreter that walks the
> compiled spec **synchronously** inside the tick (same shape as today, in the APScheduler threadpool — NOT async),
> plus **full-fidelity step tracking** for display. We are **not** building the Reconciler (no run-doc-as-source-of-truth,
> no RavenDB CAS, no reconcile poll loop). Persisted step outputs are a **passive trace**, never execution state.
> **Target:** `SocialMediaAutonomousAgents/` (backend = FastAPI + RavenDB, frontend = CRA/React).

---

## 1. What this plan builds

Today an account = `soul` (versioned voice) + ONE hardcoded, shared runbook. The typed engine
(`flatten_steps`/`run_steps`/`POST_TICK_REFERENCE_STEPS`) executes **only the SENSE/reference phase**; the entire
DECIDE→ACT path (compose → safety → regenerate → publish) is hand-written imperative code in
`interval/runner.py::_run_account_pipeline`. This plan:

1. **Makes the pipeline data** — a per-account `PipelineSpecDocument`, versioned exactly like the soul, compiled
   back into the existing `Step`/`chain`/`parallel` records and run by the existing `run_steps`.
2. **Brings the ACT path into the typed engine** — new artifacts (`COMPOSED_POST`, `SAFETY_VERDICT`,
   `PUBLISHED_POST`) + two coarse catalog tools (`compose_until_safe`, `publish_post`) so the whole loop is one walked graph.
3. **Closes the learning loop** — a real reward function, an outcome ledger keyed to the producing soul+pipeline
   version, and champion/challenger self-rewrite gated by the same validator that guards the human builder.
4. **Adds a conversational agent-builder** — chat → draft spec → validate → render graph → write.
5. **Tracks every step at full fidelity** — each step's complete I/O saved as its own `StepOutputDocument`,
   linked from the run's `PipelineRunDocument`, written via an in-process sink (works with NATS off).

## 2. Document index

| # | Doc | Owns |
|---|-----|------|
| 01 | [measure-reward](01-measure-reward.md) | `reward/reward_function.py`; composite reward; metrics-job hook |
| 02 | [outcome-ledger-attribution](02-outcome-ledger-attribution.md) | `OutcomeLedgerDocument`; `run_id`+`pipeline_hash` on `PostCreationMetrics`; engagement-job stamping |
| 03 | [tool-catalog](03-tool-catalog.md) | `ToolCatalogDocument` + **`ToolCatalog`** wrapper + `get_tool_catalog()`; deps-vs-config split |
| 04 | [pipeline-spec-and-versioning](04-pipeline-spec-and-versioning.md) | `PipelineSpecDocument`/`StepSpec`/`CompositeSpec`; `PipelineSpecRepository`; versioning; **seed** |
| 05 | [validator-and-compiler](05-validator-and-compiler.md) | `validate_spec()` (pure) + `compile_spec()`; dotted-id parity |
| 06 | [act-path-as-typed-steps](06-act-path-as-typed-steps.md) | new ArtifactKeys; `compose_until_safe`/`publish_post`; `ActLive` |
| 07 | [interpreter-wiring](07-interpreter-wiring.md) | `runner.py` load→compile→validate→`run_steps` whole graph; cost-meter wrapper |
| 08 | [step-trace-full-fidelity](08-step-trace-full-fidelity.md) | `StepOutputDocument`; in-process trace sink; `PipelineRunDocument` link list |
| 09 | [champion-challenger-self-rewrite](09-champion-challenger-self-rewrite.md) | scoring; promote/rollback; self-rewrite proposer |
| 10 | [agent-builder-api](10-agent-builder-api.md) | `POST /api/agent-builder/chat` SSE builder |
| 11 | [frontend](11-frontend.md) | builder chat; dynamic graph from spec; full step-content viewer |
| 12 | [replies-future](12-replies-future.md) | replies as a separate spec family (separable, optional) |
| 13 | [verification-and-sequencing](13-verification-and-sequencing.md) | global DoD; order; import-break warnings; rollback |
| 14 | [backend-read-routes](14-backend-read-routes.md) | `GET` spec, `POST` validate, `GET` run/step-output reads (frontend's backend) |

## 3. CANONICAL CONTRACTS — authoritative; overrides any divergence in the numbered docs

> When a numbered doc disagrees with this section, **this section wins.** Implementers read this first.
> Each contract has an id (CC-n) the docs reference.

- **CC-1 · Catalog type.** The catalog is a **`ToolCatalog` object** (not a raw list): `get(tool_id) -> ToolCatalogDocument | None`,
  `__contains__`, iterable, plus `run_for(tool_id)` returning the bound `run` callable. The **only** factory is
  `get_tool_catalog()` (in `app/pipeline/spec/catalog.py`). The name `build_catalog()` is removed everywhere.
  `validate_spec(doc, catalog)` and `compile_spec(doc, catalog=get_tool_catalog())` accept this object.
- **CC-2 · Invariant detection (no flag).** There is **no `invariant_tool`/`TOOL_INVARIANT` field**. The validator
  detects required structure purely from artifacts: a spec is valid only if (a) some step writes `SAFETY_VERDICT`
  and (b) exactly one **terminal** step writes `PUBLISHED_POST`. The cost meter is an engine wrapper (CC-9), not a tool.
- **CC-3 · `pipeline_hash` source.** `pipeline_hash` = the **walked** spec's `version_hash`, threaded from the loaded
  spec → `deps.live.pipeline_hash` → `publish_post`. There is **no `account.pipeline_version_hash` accessor**; remove
  all references. For challenger slots the walked spec is the challenger, so its hash is what gets stamped.
- **CC-4 · Published artifact.** The terminal artifact is **`ArtifactKey.PUBLISHED_POST`** carrying a `PublishedPost`
  model with a `.result` field. `PUBLISH_RESULT` does not exist; remove it.
- **CC-5 · Spec load API.** The single entry point is `PipelineSpecRepository().load_or_default(account_id, kind="post")`,
  returning the **champion** spec (or the seeded default). There is **no `load_active_spec` free function and no
  `SEED_SPEC` module constant** — docs 07/09 use the repository method. The interpreter reads only `status="champion"`.
- **CC-6 · Seed spec is 10 leaves.** `spec_from_runbook`/`default_pipeline_spec` (doc 04) emit the 8 SENSE leaves
  **plus** `compose_until_safe` (`llm.compose_until_safe`) and `publish_post` (`data.publish_post`) → a **10-leaf**
  baseline that passes CC-2. The frontend dotted-id lock fixture (doc 11) is the same 10 ids. Validating/compiling
  the seed is gated on doc 06 (the ArtifactKeys + two tools must exist first).
- **CC-7 · `ActLive` / deps.** `PostRunDeps` gains `live: ActLive`. `ActLive` carries: `account: AccountDocument`,
  `guardian`, `twitter`, `post_registry`, `max_regeneration_rounds: int`, the `bypass_*` flags,
  `copied_exclude: frozenset[str]`, `pipeline_hash: str | None`, `run_id: str`. `compose_until_safe` derives its
  `ranked_refs` **internally** from the `TIMELINE_RANKED` artifact + `copied_exclude` (applying
  `settings.max_reference_fallback_attempts`). `publish_post` **sets** `run_id`/`pipeline_hash` on `PostCreationMetrics`
  and reads `followers_at_post` from the `ACCOUNT_BUNDLE` artifact. Doc 06 defines `ActLive`; doc 07 populates it.
- **CC-8 · `_internal.*` primitives.** Steps with no catalog tool (today: `collect_external_references`) use a
  `_internal.<name>` tool_id. The validator **skips** the reads-closure check for `_internal.*` and sources their
  reads/writes from the spec node; the compiler binds `_internal.collect_external` → `steps.collect_external_references`.
  Listed in `INTERNAL_PRIMITIVES` (doc 05).
- **CC-9 · Cost meter is real + non-bypassable.** `run_steps` wraps every leaf with an engine-owned cost meter
  (`core/cost_meter.py`). `compose_until_safe`/`publish_post` (and any LLM tool) report token usage from
  `claude_client`; doc 07 owns a `tokens→USD` helper using a configurable `settings.cost_per_1k_tokens_usd`
  (no hardcoded model price). The ceiling trips on real spend; the spec cannot remove it.
- **CC-10 · Builder API.** Canonical: `POST /api/agent-builder/chat`, body
  `BuilderChatRequest{account_id, mode, messages[], approve}`, SSE events
  `assistant_message | validation_errors | spec_preview | spec_written | error | done`. The frontend (doc 11) targets this.
- **CC-11 · Backend read routes (doc 14).** `GET /api/accounts/{id}/pipeline/spec[?status]`,
  `POST /api/accounts/{id}/pipeline/spec/validate`, `GET /api/pipeline/runs/{run_id}` (trace chain), and
  `GET /api/pipeline/runs/{run_id}/steps/{step_id}` (full step output). Thin reads over `PipelineSpecRepository` (04),
  `validate_spec`+`get_tool_catalog` (05/03), `StepOutputRepository` (08). Sequenced before doc 11.
- **CC-12 · Spec families by `kind`.** `PipelineSpecRepository.document_id`/`load`/`save` take `kind="post"` (default);
  `kind="reply"` (doc 12) coexists as a separate family. Champion/challenger status is per `(account_id, kind)`.
- **CC-13 · Package marker.** `app/pipeline/spec/__init__.py` is created by the first slice in the sequence (doc 03);
  later slices treat it as REUSED.

## 4. Recommended implementation order

`01 → 03 → 04 → 05 → 02 → 08 → 06 → 07 → 14 → 09 → 10 → 11 → 12`, with **13** as the live checklist throughout
(doc **13 §2** owns this ordering and its dependency rationale; this line mirrors it). The load-bearing invariants:
types + pure functions first (`01,03,04,05`); `02` (the `PostCreationMetrics` field add) **before `06/07`**, which stamp those
fields; `08` (trace seam) **before `06/07`** so it is verified on the 8 SENSE leaves first; the `06 → 07` import-break unit
done atomically; then **`14`** (backend read-routes, **CC-11**) **after `08` and the `06→07` unit, before `11`**.

**Import-break warning (mirrors `soul-pipeline` §5/§7):** the tree is **import-broken from doc 06 until doc 07** —
doc 06 adds the ACT ArtifactKeys/tools and relocates the imperative compose/publish body that `runner.py` and
`reference_phase.py` still call. Land **03 → 04 → 05 → 06 → 07 back-to-back** (plus the call-site sweep:
`tests/unit/test_pipeline_runbook.py`, `tests/test_orchestrator.py`) and expect a green `pytest` **only after 07**.
Do not run `py_compile`/`pytest` mid-unit and conclude a failure means you broke something.

`01` (reward, keyed by `tweet_id`) and `08` (trace sink) are independent and can land early. `02` must land before
`06/07` (they stamp the fields `02` adds). `12` is separable and optional.

## 5. Global Definition of Done

- `cd SocialMediaAutonomousAgents/backend && python -m pytest -q` → green (incl. new + updated tests).
- `python -m py_compile` clean across all touched backend files.
- `cd SocialMediaAutonomousAgents/frontend && npm run build` → clean.
- `docker compose up -d --build` → all services healthy.
- **Functional:** current posting behavior preserved end-to-end; `POST_TICK_REFERENCE_STEPS` round-trips through a
  spec (seed → `validate_spec` ok → `compile_spec` → same dotted ids); `validate_spec` **rejects** a crafted bad spec
  (dangling read, no terminal `PUBLISHED_POST`); a composed post still posts to X; full `StepOutputDocument`s are
  written and linked from the run's `PipelineRunDocument` with **no truncation**; the ledger row is stamped with the
  walked `run_id`+`pipeline_hash`; reward is computed for a polled post.

## 6. How this plan is executed

Hand this folder to the autonomous loop-prompt (the one drafted earlier). The loop reads this `00-overview.md`
**first** and treats §3 (Canonical Contracts) as authoritative, then works the order in §4, delegating each unit to a
subagent, verifying against §5, and cataloging any genuine blocker to `docs/plans/interpreter-pipeline/BLOCKERS.md`.

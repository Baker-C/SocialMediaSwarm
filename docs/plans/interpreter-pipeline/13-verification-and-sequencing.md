# 13 — Verification, Sequencing & Rollback (the acceptance procedure)

> **Status:** Ready to execute. Authored cold against the live tree on branch `feat/platform-overhaul`; every command, path, settings key, and container name below was verified against the actual code/compose files (not memory).
> **Scope:** No production-code changes here — this is the **global Definition of Done**, the **recommended implementation order** across docs 01–12 (with dependency rationale and explicit import-break warnings), per-slice DoD cross-references, and the **rollback strategy**. Run this after implementing the slices it sequences.
> **Target project:** `SocialMediaAutonomousAgents/` (backend = FastAPI + RavenDB + in-process APScheduler; frontend = CRA/React).
> **DB reality:** exactly **one** account today — `JohnJames_News`. RavenDB has NO multi-doc transactions and NO CAS/If-Match (`backend/app/infrastructure/ravendb_http.py:103-110`); the Interpreter needs none.

This is the **last doc in the set**. It owns nothing the siblings define — it *verifies* them as a whole and tells the implementer (a subagent loop) the order to build them in so the tree is never gratuitously broken and every claim is checked end-to-end.

---

## 0. Where this doc sits

| I depend on (defined elsewhere) | Doc | What I verify about it |
|---|---|---|
| `post_reward()` / `account_avg_reward()` + `avg_post_reward` field | **01** | reward computed; in `[0,1]`/`None`; zero new X calls |
| `OutcomeLedgerDocument` + `run_id`/`pipeline_hash` join on `PostCreationMetrics` | **02** | ledger stamped at publish with `run_id`+`pipeline_hash`; filled by jobs |
| `ToolCatalogDocument` + injected/proposable split | **03** | six tools introspected; honest config split |
| `PipelineSpecDocument` + `compute_pipeline_hash` + champion/challenger | **04** | spec round-trips a version; seed reproduces the 10 dotted ids (8 SENSE + 2 ACT leaves it appends) |
| `validate_spec` / `compile_spec` (pure) | **05** | validator REJECTS a crafted bad spec; compiler dotted-id lock |
| `compose_until_safe` / `publish_post` tools + 3 ACT artifacts | **06** | composed post still posts; idempotency marker blocks double-post |
| `_run_account_pipeline` rewrite + `engine_invariants` + `CostMeter` | **07** | one `run_steps` walk; cost ceiling non-bypassable; behavior preserved |
| `StepOutputDocument` + `StepTraceSink` (NATS-independent) | **08** | full StepOutputDocuments written + linked from the run doc, NATS OFF |
| champion/challenger evaluator + `spec_status` threading | **09** | self-rewrite respects reward `None`; promotion/rollback ride 04 §6c sequential puts |
| `POST /api/agent-builder/chat` SSE builder backend | **10** | reachable on the live stack; validates before activate; auth-gated |
| spec-driven flow graph + run-trace viewer + builder page | **11** | nodes derive from the spec; trace renders untruncated; builder consumes 10's contract |
| replies pipeline (`pipeline_kind`) | **12** (OPTIONAL) | not on the core critical path; sequenced last, gated behind 03–08 |
| **backend read-route slice** (`GET .../pipeline/spec[?status]`, `POST .../pipeline/spec/validate`, `GET /pipeline/runs/{run_id}`, `GET /pipeline/runs/{run_id}/steps/{step_id}`) | **14** (per CC-11) | the four thin reads doc 11's viewer/graph need; **sequenced after 08, before 11 (§2 step 9) or B5/B-frontend cannot be verified** |

> **Doc-count note (honest):** the folder holds the full set `01`–`14`. The role→filename mapping (verified against the actual filenames, because earlier drafts used drifting numbers): **09** = champion/challenger self-rewrite (`09-champion-challenger-self-rewrite.md`), **10** = agent-builder API (`10-agent-builder-api.md`, the `POST /api/agent-builder/chat` SSE backend), **11** = frontend (`11-frontend.md`, spec-driven graph + run-trace viewer + builder page), **12** = replies (`12-replies-future.md`, explicitly OPTIONAL/post-core), **14** = backend read-routes (`14-backend-read-routes.md`, the pipeline read endpoints, per **CC-11**). This doc does not invent their internals — it places them and gives the global gates they must also pass. **The backend read-route slice is owned by doc 14 (CC-11)** and is sequenced here at §2 step 9; see §0.1.

### 0.1 — The backend read-route slice (doc 14, per CC-11; §2 step 9 sequences it)

Doc 14 (`14-backend-read-routes.md`, per **CC-11**) owns — and docs 10 (§553) and 11 (§3.1/§3.2, §520) both flag and consume read-only — the thin read routes the frontend trace viewer and spec graph require. They are one-line handlers over methods docs 04/05/03/08 already ship; the work is **route registration**, not logic. Because doc 11's `RunTraceViewer` and `flowFromSpec` graph cannot fetch their data without them, and §4.B B5 inspects step-output reads, **this slice is on the critical path for frontend verification and MUST land before doc 11**. CC-11's contract (so the implementer has zero questions):

| Route | Handler body | Returns / 404 | Source doc |
|---|---|---|---|
| `GET /api/accounts/{account_id}/pipeline/spec?status=champion` | `await asyncio.to_thread(PipelineSpecRepository().load_or_default, account_id, status)` → `.model_dump()` | never 404s — `load_or_default(account_id, status="champion")` returns the seeded baseline when no doc exists (04 §6b/§359); the `status` query param is a `Literal["champion","challenger"]` defaulting to `champion` (04 §128) | 04 §6b |
| `POST /api/accounts/{account_id}/pipeline/spec/validate` | `validate_spec(PipelineSpecRepository().load_or_default(account_id, status), get_tool_catalog()).model_dump()` | the `ValidationReport` (05 §5.2) with `.ok`/`.errors` | 05 §5.2 + 03 |
| `GET /api/pipeline/runs/{run_id}` (trace chain) | **already exists** — `pipeline_runs.py:45`, handler `get_run` (verified). Doc 14 REUSES it for the trace header; no new code. | the `PipelineRunDocument` header + `step_links[]`; 404 if unknown | 08 §10 |
| `GET /api/pipeline/runs/{run_id}/steps/{step_id}` | `await asyncio.to_thread(StepOutputRepository().get, run_id, step_id)` → `.model_dump()` | the `StepOutputDocument`; **404 if `None`**. The dotted `step_id` (e.g. `summarize_for_compose.analyze_external_references.rank_external_references`) contains no slash, so a single path segment is safe (08 §5) | 08 §5 |

**Implementation shape (doc 14 owns):** a new `backend/app/api/routes/pipeline_spec.py` for the two spec routes (mirroring `pipeline_runs.py` exactly — `router = APIRouter()`, module-level repo, `asyncio.to_thread` for the blocking load), registered in `main.py` with `app.include_router(pipeline_spec.router, prefix="/api", tags=["pipeline-spec"], dependencies=_auth)` (mirrors `main.py:183`); the new `GET /pipeline/runs/{run_id}/steps/{step_id}` step-output route is added in the existing `pipeline_runs.py` alongside `get_run` (the trace-header route it reuses). **Prerequisites:** 04 (`PipelineSpecRepository.load_or_default`), 05 (`validate_spec`), 03 (`get_tool_catalog`), 08 (`StepOutputRepository.get`) — so doc 14 is sequenced **after 08 and after the 06→07 unit** (§2 step 9), before doc 11.

---

## 1. The single most important sequencing truth (read before ordering anything)

**The tree is import-broken from the moment a doc deletes or re-signs a symbol its consumers still reference — and it stays broken until every consumer is swept.** This is the exact failure mode soul-pipeline `00-overview.md §5` documents ("the earlier claim that *each step compiles independently* is **wrong** … the tree is import-broken from Task 01 until its consumers are updated") and `06-compose-pipeline.md` §F.2 lives ("without this edit the runner raises `AttributeError` before composing anything"). The Interpreter set has the **same shape of hazard**, concentrated in three places:

1. **Doc 07 deletes `app/interval/reference_phase.py` and rewrites `_run_account_pipeline`.** The instant `reference_phase.py` is deleted, every importer breaks: `interval/runner.py:24` (the `from app.interval.reference_phase import run_reference_phase` line — this is what `py_compile` hits first; the call site is `:228`), `tests/test_reference_fallback.py:5` (imports `ReferencePhaseResult`, patches `run_reference_phase` at `:92`), `tests/unit/test_reference_phase.py:5` (imports `ranked_refs_from_runbook`), and `tests/test_runner_post_guard.py:42` (patches `run_reference_phase`). **`py_compile` and `pytest` will be RED across these until 06 (the tools the new runner calls) AND the moved tests land.** Do **not** run `pytest` mid-07 and conclude you broke something — a failure there is *expected* until 06+07+the test moves are all in.

2. **Doc 06 appends ACT artifacts and tools; doc 07 consumes them.** `compose_until_safe`/`publish_post` (06) write `COMPOSED_POST`/`SAFETY_VERDICT`/`PUBLISHED_POST`; the rewritten runner (07) and the validator's R6/R7 (05) read them. If 07 lands before 06, `from app.pipeline.tools.llm import compose_until_safe` is an `ImportError` and `ArtifactKey.COMPOSED_POST` does not exist. **06 must precede 07.**

3. **Doc 06 appends the two ACT leaves to `POST_TICK_REFERENCE_STEPS`, and unit tests hard-assert the OLD 8-leaf / 5-top-level shape.** `06 §7.1` appends `compose_until_safe` + `publish_post` `Step`s to the runbook tuple, so `flatten_steps(POST_TICK_REFERENCE_STEPS)` yields **10** ids and the top level grows to **6**. Two equality assertions in `tests/unit/test_pipeline_runbook.py` go RED the instant 06 lands and are **not** reference_phase importers, so the §4.A grep guards will not surface them: `test_runbook_step_names_are_readable` (`:16-27`, asserts the flattened list `== [the 8 SENSE ids]`) and `test_runbook_top_level_step_ids` (`:30-38`, asserts `top_ids == [..., 'summarize_for_compose']`, 5 entries). **Doc 06 §7.5 explicitly owns these updates** (and the `test_orchestrator.py` patch-target move) — verified `06 §54`/`§7.5` list both files. The fix: append `compose_until_safe`, `publish_post` to both expected lists (the flattened list gains them as bare top-level ids per `flatten_steps`; the top-level list gains them after `summarize_for_compose`). A third test in the same file (`test_runbook_reference_analysis_with_mocked_deps`, `:41-75`) calls `run_steps(POST_TICK_REFERENCE_STEPS, ...)` directly; after 06 it will additionally execute the two ACT leaves, so it must be **narrowed to the SENSE prefix** (08 §7b confirms `run_steps` outside `run_account_pipeline` sees `sink=None` and is byte-identical, but the ACT leaves still *run* and need `deps.live`/`deps.guardian`, which this mocked test does not provide — pass only the SENSE steps to `run_steps`). All of this is part of the same import-break unit as §1.1/§1.2; expect it RED until 06 closes. **`test_orchestrator.py` is the other casualty the old 07 test-move list omitted** — 06 §7.5 owns it (it patches `app.interval.runner.compose_formatted_post`, which 06/07 move into `compose_until_safe`, and asserts `'tweet' in out`, which holds because `PUBLISHED_POST.result` carries the full `finalize_post` dict; 06 §7 / 07 §2.6).

**Mitigation rule (the same one soul-pipeline used):** the docs that break the tree (06 → 07, and their test moves/updates — including `test_pipeline_runbook.py:16-38` above) are implemented **back-to-back as one unit**, and you expect a green `pytest` only *after* the unit closes — never mid-sequence. Everything *before* that unit (01–05, 08) is genuinely additive and each compiles + tests green on its own.

---

## 2. Recommended implementation order (with dependency rationale)

```
01  →  03  →  04  →  05  →  02  →  08  →  ┌ 06  →  07 ┐(one unit)  →  14  →  09  →  10  →  11  →  12
                                          └ +test moves┘  (read-routes, §0.1)
   ── additive, each green on its own ──   ── import-break unit ──    ── built on a live interpreter ──
```

> **Reconciliation with `00-overview.md §4` (authoritative).** The overview's one-line order (`01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 14 → 09 → 10 → 11 → 12`) and this table agree on the **invariants that matter**: 02 before 06/07 (it owns the `PostCreationMetrics` fields they stamp), 03/04/05 before 06/07, 06→07 atomic, **08 before 06/07** (verify the trace seam on the 8 SENSE leaves first — Decision Defense below), and **14 after the 06→07 unit, before 11**. The mild re-orderings here (02 right after 05; 08 just before the import-break unit) are the *operational* refinement this doc owns and §00 §4 has been updated to mirror; both place doc 14 at the same point relative to its prerequisites (after 08, after 06→07, before 11).

| Step | Doc | Why here | Breaks the tree? |
|---|---|---|---|
| 1 | **01 — reward** | Pure greenfield (`app/reward/`), one additive field, one job line. Nothing imports it yet. The reward scalar is the contract 02/11 consume. | No — purely additive. |
| 2 | **03 — tool catalog** | Read-only introspection over the tool layer (`app/pipeline/spec/catalog.py`). Touches **no** tool file. 04/05 reference its injected/proposable split. | No — additive, read-only. |
| 3 | **04 — spec model + versioning** | Defines `PipelineSpecDocument`/`StepSpec`/`CompositeSpec` + `compute_pipeline_hash` + the seed. Everything downstream imports these types. Must precede 05 (compiler lowers them) and 02 (which reads `pipeline_hash` from `load_or_default(...).version_hash`). | No — new model/service/repo files. |
| 4 | **05 — validator + compiler** | Pure functions over 04's spec + 03's catalog. Needs both. Its dotted-id lock test guards the frontend contract before any runtime wiring. | No — two pure modules + tests. |
| 5 | **02 — outcome ledger + attribution** | Adds `run_id`+`pipeline_hash` to `PostCreationMetrics` and the ledger. `pipeline_hash` is the loaded spec's `version_hash` (04's repo+hash, NOT an account accessor — none exists); the join is read by 11. Additive `None` fields — no existing TrackedPost breaks. | No — additive fields + new model/repo + one job line each. |
| 6 | **08 — full-fidelity step trace** | Adds `StepOutputDocument` + `StepTraceSink` + a step-boundary hook (`record_step_trace` in `_run_step_with_progress`). Hooks the **existing** SENSE engine, so it lands **before** the runner rewrite and is verified on the 8 SENSE leaves first; 06's ACT steps then flow through the *same* hook automatically. | No — one new field on the run doc + one `record_step_trace` call. The trace-sink contextvar defaults to `None` (08 §7c), so `record_step_trace` no-ops and `run_steps` is byte-identical wherever the sink is unset (e.g. unit tests calling `run_steps` directly). |
| 7 | **06 — ACT path as typed steps** | The crux. Adds 3 `ArtifactKey`s + 2 tools + `PostRunDeps.live`. **Opens the import-break unit** (07 consumes its tools/artifacts). Appending the two ACT leaves to `POST_TICK_REFERENCE_STEPS` (06 §7.1) makes `tests/unit/test_pipeline_runbook.py:16-38` and `test_orchestrator.py` go RED — **06 §7.5 owns those test edits** (§1.3). | **Yes** (with 07). 07 will delete `reference_phase.py`. |
| 8 | **07 — interpreter wiring** | Rewrites `_run_account_pipeline` to one `run_steps` walk, deletes `reference_phase.py`, adds `CostMeter` + `engine_invariants`. **Closes the unit; move the 3 `reference_phase` tests (`test_reference_fallback.py`, `test_runner_post_guard.py`, `unit/test_reference_phase.py`) and confirm the `test_pipeline_runbook.py` + `test_orchestrator.py` edits from step 7 (06 §7.5) are in.** | **Yes** — green only after this + test moves/updates. |
| 9 | **14 — backend read-routes** (§0.1, CC-11) | The thin pipeline read routes (`GET .../pipeline/spec[?status]`, `POST .../pipeline/spec/validate`, the reused `GET /pipeline/runs/{run_id}` trace header, and the new `GET /pipeline/runs/{run_id}/steps/{step_id}`). Owned by **doc 14** (CC-11), required by doc 11's viewer/graph and §4.B B5. Needs 04/05/03/08 (all merged) + the live interpreter for real step-output data. New `pipeline_spec.py` route file + one `include_router` line; one new handler in `pipeline_runs.py`. | No — new route file + registration; no symbol re-signed. |
| 10 | **09 — champion/challenger self-rewrite** | Consumes the live interpreter + `validate_spec`/`compile_spec` (05) + `avg_post_reward`/ledger (01/02). Adds the `spec_status` threading (its own §2). | No — additive on a green base. |
| 11 | **10 — agent-builder API** | The `POST /api/agent-builder/chat` SSE backend; calls `validate_spec`/`compile_spec` (05) + `build_tool_catalog` (03). Canonical owner of the builder contract doc 11 consumes. | No — new route + types. |
| 12 | **11 — frontend** | Spec-driven flow graph + run-trace viewer + builder page. Needs the read routes (step 9) + the builder backend (10) + the live trace (08+06/07). Built last on the green base. | No — frontend only. |
| 13 | **12 — replies (OPTIONAL)** | Post-core; gated behind 03–08 and 06's `PostRunDeps`/`ActLive` extension (12 §11). Not on the critical path. | No — additive, optional. |

**Rationale in one line:** *types and pure functions first (01,03,04,05), then the additive persistence/attribution seams (02,08), then the one unavoidable import-break unit (06→07) done atomically, then the read-route slice (doc 14, §0.1/CC-11) and everything that needs a running interpreter (09–12).*

> **Decision Defense — why 08 before 06/07, not after.** 08's hook lives in `_run_step_with_progress` (`backend/app/pipeline/_runbook_engine.py:42-148`), which already runs the 8 SENSE leaves today. Landing 08 first lets you verify "full StepOutputDocuments written + linked, NATS OFF" against the *current* pipeline — a clean, isolated check — before the runner rewrite changes what flows through the engine. When 06/07 add `compose_until_safe`/`publish_post` to the graph, they pass through the identical hook and are captured for free (08 §8). Sequencing 08 after 07 would conflate "did the trace seam work?" with "did the runner rewrite work?" into one harder-to-bisect failure.

> **Decision Defense — why 02 after 05, not adjacent to 01.** 02's attribution stamp reads `pipeline_hash` from the **loaded spec's `version_hash`** — `PipelineSpecRepository().load_or_default(account_id).version_hash` (02 §3.3, 07 §7) — which is 04's deliverable. **There is no `account.pipeline_version_hash` accessor** (verified `account.py:366-387`: only `voice_version_*` exist; the spec lives in a separate `pipelinespecs/{account_id}` doc per 04, deliberately off the account). 02's `compute_reward` is independent of 01's richer `post_reward` (02 deliberately uses the simpler engagement-rate scalar for the ledger — see 02 §6). So 02 only *hard*-depends on 04; placing it right after 05 keeps the spec-versioning context fresh and lets Slice A (the join) ship the moment 04's repo + hash exist.

---

## 3. Per-slice Definition of Done (cross-reference index)

Each sibling doc owns its detailed DoD; this table is the **roll-up the implementer checks off**, with the section to consult. Do not duplicate the criteria here — trust the owning doc and verify against it.

| Doc | Slice DoD lives in | The one load-bearing acceptance to spot-check |
|---|---|---|
| 01 | `01-measure-reward.md` §7 | `run_metrics_job` writes `accountmetrics/JohnJames_News.avg_post_reward` ∈ `[0,1]` or absent; **grep the diff: zero new `tw.`/`get_posts_metrics`/`requests`**. |
| 02 | `02-outcome-ledger-attribution.md` §3.4, §4.5 | `trackedposts/JohnJames_News-{tid}.creation_metrics.run_id` == the matching `pipelineruns/{run_id}`; `outcomeledger/JohnJames_News-{tid}` exists with the three hashes/ids. |
| 03 | `03-tool-catalog.md` §8 | `build_tool_catalog()` returns **exactly six** tools; only `top_n`/`max_results_per_query`/the four compose soul fields are `config`/`literal`. |
| 04 | `04-pipeline-spec-and-versioning.md` §8 | seed's compiled+flattened steps == the **10** dotted ids `flatten_steps(POST_TICK_REFERENCE_STEPS)` yields after 06 (8 SENSE + the 2 ACT leaves the seed appends, 04 §7/§460); `v1` revision archived; re-run idempotent. |
| 05 | `05-validator-and-compiler.md` §9 | `flatten_steps(compile_spec(baseline)) == flatten_steps(POST_TICK_REFERENCE_STEPS)` id-for-id; each of the 12 error codes reachable + tested. |
| 06 | `06-act-path-as-typed-steps.md` §3,§5,§7 DoD | `_run_account_pipeline` no longer contains a `compose_formatted_post` call or a `for reg_round` loop; `publish_post` calls `finalize_post` **at most once** per `(run_id, account_id)`. |
| 07 | `07-interpreter-wiring.md` §8 | one `run_steps` walks SENSE+ACT; `run_ctx.run_id == current_run_id()`; cost ceiling trips → publishes nothing + releases guards; `grep -r reference_phase app/` empty. |
| 08 | `08-step-trace-full-fidelity.md` §10 | NATS OFF → one `StepOutputDocument` per leaf + one `PipelineRunDocument` with ordered `step_links`; a `timeline_references` payload >8000 chars stored whole (no `[truncated]`). |
| 14 (read-routes) | `14-backend-read-routes.md` §DoD (contract pinned in this doc §0.1 / CC-11) | `GET /api/accounts/JohnJames_News/pipeline/spec` returns the champion spec `.model_dump()` (never 404s); `GET /api/pipeline/runs/{run_id}/steps/{step_id}` returns the full untruncated `StepOutputDocument` (404 on unknown). |
| 09 | `09-champion-challenger-self-rewrite.md` §DoD | self-rewrite respects reward `None` (does not promote on an empty/unscored ledger); promotion + auto-rollback ride 04 §6c's sequential puts; `spec_status` threads interval_job→run_tick→build_tick_context→`TickContext.spec_status`. |
| 10 | `10-agent-builder-api.md` §8 | `POST /api/agent-builder/chat` reachable (200/stream) on the live stack; an unauthenticated call is rejected by `require_auth`; `approve:true` writes a champion/challenger and emits `spec_written`. |
| 11 | `11-frontend.md` §9 | `npm run build` clean; flow nodes derive from the spec (`flowStepIds(baselineSpec)` == the 10 dotted ids); `RunTraceViewer` renders the full untruncated chain (NATS OFF); builder page consumes doc 10's contract. |
| 12 (OPTIONAL) | `12-replies-future.md` §DoD | not on the core critical path — verify only if replies are actually built; depends on 06's `PostRunDeps`/`ActLive` (12 §11). |

---

## 4. Global Definition of Done

Two tiers. **Tier A (static/build/health)** is the mechanical gate every slice and the final state must pass. **Tier B (functional)** is the set of end-to-end behaviors that prove the Interpreter actually works — these are the brief's named checks.

### 4.A — Static + build + health (mechanical gate)

```bash
# 1. Backend syntax — every file the set touched (adjust per the slices actually landed)
cd SocialMediaAutonomousAgents/backend
python -m py_compile \
  app/reward/reward_function.py \
  app/models/metrics.py \
  app/models/tracked_post.py app/models/outcome_ledger.py \
  app/models/tool_catalog.py app/models/pipeline_spec.py app/models/pipeline_revision.py \
  app/models/step_output.py app/models/pipeline_run.py \
  app/services/outcome_ledger_repository.py \
  app/services/pipeline_version_service.py app/services/pipeline_revision_repository.py \
  app/services/pipeline_spec_repository.py app/services/step_output_repository.py \
  app/pipeline/spec/catalog.py app/pipeline/spec/validator.py app/pipeline/spec/compiler.py \
  app/pipeline/tools/llm/compose_until_safe.py app/pipeline/tools/data/publish_post.py \
  app/pipeline/types/artifacts.py app/pipeline/services/deps.py \
  app/pipeline/services/steps.py app/pipeline/runbooks/post_tick.py \
  app/pipeline/events/step_trace.py app/pipeline/_runbook_engine.py \
  app/core/cost_meter.py app/core/config.py \
  app/interval/runner.py app/interval/orchestration/post_tick.py

# 2. Backend tests — full run (the belt-and-suspenders catch for any orphaned importer)
python -m pytest -q

# 3. The deleted module is gone and nothing imports it (07's deletion)
test ! -f app/interval/reference_phase.py && echo "reference_phase.py removed OK"
```

```bash
# 4. Frontend type-check + build (09/12 add the spec UI + the new flow nodes)
cd SocialMediaAutonomousAgents/frontend
npm run build      # must compile; no new TS errors
```

```bash
# 5. Stack rebuild + health (container names verified in docker-compose.yml)
cd SocialMediaAutonomousAgents
docker compose up -d --build
docker ps --format "table {{.Names}}\t{{.Status}}"
#   expect: social-media-backend, social-media-frontend, social-media-nats healthy; ravendb reachable
```

**Grep guards (should return nothing):**
```bash
cd SocialMediaAutonomousAgents/backend
# 07 deleted reference_phase — no live import of it may remain
grep -rn "reference_phase\|ReferencePhaseResult\|run_reference_phase" app/
# 08's trace path must NOT reuse the TRUNCATING capture
grep -rn "capture_artifacts(" app/pipeline/events/step_trace.py   # must be EMPTY (use capture_artifacts_full)
# 07's rewritten runner must not still hand-roll compose/regen
grep -n "compose_formatted_post\|for reg_round in range" app/interval/runner.py   # must be EMPTY
```

> **Expected-RED window (do not panic):** if you run §4.A **between** doc 06 and the close of doc 07, step 2 (`pytest`) and step 3 (the `reference_phase.py` removal check) and the first grep WILL fail — `reference_phase.py` is mid-deletion and its importers are mid-sweep (see §1.1), AND `tests/unit/test_pipeline_runbook.py:16-38` is mid-update for the 8→10 leaf growth (see §1.3). Specifically, the moment 06 appends the two ACT leaves, `test_runbook_step_names_are_readable` and `test_runbook_top_level_step_ids` go RED on the old hard-coded id lists until you update those two assertions; this is **expected**, not a regression. The mechanical gate is only meaningful at the **boundaries** of the import-break unit: green before 06 opens it, green after 07 + the test moves/updates close it. Never inside it.

### 4.B — Functional checks (the brief's named acceptance, end-to-end)

All seven run against the live stack with `JohnJames_News`. Trigger a real run one of two verified ways (both confirmed present on this branch):

1. **The force-post script** — `pwsh SocialMediaAutonomousAgents/scripts/docker-forced-post.ps1 JohnJames_News`. **The account id is a mandatory positional arg** (`$AccountIds`, `docker-forced-post.ps1:3`); omitting it makes PowerShell prompt and the run never fires. The script `docker compose exec -T backend python scripts/create_forced_post.py --force-now JohnJames_News` — i.e. it runs the forced post *inside the container*, it does NOT hit the HTTP route.
2. **The force-post SSE route** — `POST /api/accounts/JohnJames_News/force-post` (registered at `backend/app/main.py:183`, handler `backend/app/api/routes/force_post.py:76`), or the dashboard "force" control wired to it. Use this when you want to watch the live SSE step-progress stream.

Either path drives the same `_run_account_pipeline`; pick the script for a headless one-shot, the route for the streamed view.

| # | Check (verbatim from the brief) | How to verify | Owning doc |
|---|---|---|---|
| B1 | **Current post behavior preserved end-to-end** | Force-post; a tweet is published with the same observable shape as before (body composed, guardian-approved, posted to X), OR a `rejected`/`skipped` return with `references_tried` when no body passes. Compare a pre-change posted body to a post-change one — same persona, punctuation auto-fix applied, media URL intact. | 06 §8, 07 §2.6 |
| B2 | **POST_TICK round-trips through a spec** | `python -m scripts.seed_pipeline_spec` then confirm `pipelinespecs/JohnJames_News` exists; `flatten_steps(compile_spec(load_or_default("JohnJames_News")))` equals `flatten_steps(POST_TICK_REFERENCE_STEPS)` id-for-id — the **10 dotted ids** (8 SENSE + `compose_until_safe` + `publish_post`; the seed appends the two ACT leaves per 04 §7/§8, and 06 appends the same two to `POST_TICK_REFERENCE_STEPS`, so both sides are 10). I.e. the live pipeline is now *driven by the seeded spec doc*, not the hardcoded tuple. | 04 §8, 05 §6.1 |
| B3 | **Validator REJECTS a crafted bad spec** | `validate_spec(bad, catalog).ok is False` for each crafted defect: a leaf with `tool_id="data.does_not_exist"` → `unknown_tool`; a leaf reading `TIMELINE_RANKED` placed before its ranker → `dangling_read`; the publish leaf removed → `no_terminal_published`; the `compose_until_safe` leaf removed (so no leaf's **catalog `writes`** includes `safety_verdict` — note 05 uses the closed-catalog static `writes`, NOT an `invariant_tool` flag, which doc 03 does not ship; 05 §207/§529) → `missing_safety_invariant`. (Covered by `tests/unit/pipeline/test_spec_validator.py`.) | 05 §5, §8 |
| B4 | **A composed post still posts** | The B1 force-post that produced a body ⇒ a `trackedposts/JohnJames_News-{tweet_id}` row and a live tweet id in the return dict. This is B1 from the *publish* angle: `publish_post` → `finalize_post` → `ctx.twitter.post_tweet` fired exactly once. | 06 §5.2, 07 §2.6 |
| B5 | **Full StepOutputDocuments written + linked from the run doc** | With **NATS OFF** (`nats_enabled=false`): force-post ⇒ collection `StepOutputs` has one `stepoutputs/{run_id}/{step_id}` per flattened leaf (8 SENSE + `compose_until_safe` + `publish_post` = 10 after 06/07), each with full untruncated `inputs`/`outputs`; `pipelineruns/{run_id}.step_links` is ordered by `seq`, `step_count == len(step_links)`, and every `doc_id` resolves via `StepOutputRepository.get()`. **Window caveat:** if you run B5 in the 08-before-06/07 window (§2 step 6 done, step 7-8 not yet), only the **8 SENSE** docs exist — the imperative ACT path emits via the orchestrator scope and does NOT pass through the trace hook (08 §8). An 8-row chain there is **correct for that window**, not a missing-ACT bug; the 10-row count is the *final-state* assertion. | 08 §10 |
| B6 | **Ledger stamped with run_id + pipeline_hash** | After B4: `outcomeledger/JohnJames_News-{tweet_id}` exists with `run_id` == the run's, `soul_hash` == `account.voice_version_hash`, and `pipeline_hash` == the **loaded spec's** `version_hash` (`PipelineSpecRepository().load_or_default("JohnJames_News").version_hash`, NOT an `account.*` field — there is no `account.pipeline_version_hash`; 07 §7), `reward: null`, `raw_metrics: {}`. Also assert `creation_metrics.run_id`/`.pipeline_hash` on the TrackedPost match (the join). On a brand-new account whose spec has never been `save()`d, `pipeline_hash` may legitimately be `None` (the "baseline" bucket, 02 §6) — for `JohnJames_News` after B2 seeds `pipelinespecs/JohnJames_News`, it is non-`None`. | 02 §3.4, §4.5 |
| B7 | **Reward computed** | Run `run_metrics_job()` (or wait for the hourly cron `CronTrigger(minute="10")`) after the post has impressions; `accountmetrics/JohnJames_News.avg_post_reward` is a float ∈ `[0,1]` (or absent if all posts unpolled), and the ledger row's `reward` advanced to the post's `engagement_rate`. **No new X request fired** during the job. | 01 §7, 02 §4.4 |

**One-shot functional smoke (after the full stack is up, NATS OFF for B5):**
```bash
# trigger (account id is REQUIRED — see §4.B intro)
pwsh SocialMediaAutonomousAgents/scripts/docker-forced-post.ps1 JohnJames_News
# inspect (RavenDB Studio or the HTTP API; routes are under /api)
#   B2: pipelinespecs/JohnJames_News              → seeded spec present
#   B4: trackedposts/JohnJames_News-{tweet_id}     → posted
#   B5: StepOutputs collection                     → 10 docs for {run_id}, untruncated
#   B5: pipelineruns/{run_id}.step_links           → ordered, count matches
#   B6: outcomeledger/JohnJames_News-{tweet_id}    → run_id + pipeline_hash stamped
# then drive reward:
docker exec -it social-media-backend python -c "from app.jobs.metrics_job import run_metrics_job; run_metrics_job()"
#   B7: accountmetrics/JohnJames_News.avg_post_reward ∈ [0,1] or absent; ledger.reward advanced
```

> **Cost-ceiling non-bypass spot-check (07 invariant, worth running once):** set `pipeline_cost_ceiling_usd` low (e.g. `0.01`) and force-post; the run halts via `CostCeilingExceeded`, **publishes nothing**, releases all guards (`release_post_pipeline_guards` ran — verify the slot/file locks are gone), and the trace shows the blocked step `failed`. Reset to the default `0.50` after. This proves the cost ceiling is an engine invariant the spec cannot remove (07 §3, §4).

---

## 5. Rollback strategy

The Interpreter is **code + additive data**. Nothing here destructively migrates an existing document's shape (unlike soul-pipeline, which dropped `voice`). That makes rollback materially simpler — but two seams (07's runner rewrite, 04's seeded spec) deserve explicit handling.

### 5.1 Code rollback

`git revert` the implementation commits in **reverse dependency order** (12→…→01, or just revert the whole feature merge). The reverted runner reads `POST_TICK_REFERENCE_STEPS` + the imperative compose/publish tail again; it never reads `pipelinespecs/*`, so leftover spec docs are inert. Specifically:

- **07 is the only revert that restores a deleted file.** Reverting 07's commit re-creates `interval/reference_phase.py` and the imperative `_run_account_pipeline`. Because 06's tools (`compose_until_safe`/`publish_post`) become unused after the revert, you may leave them in place (dead, harmless) or revert 06 too. The slot/file/RavenDB locks (`post_guard.py`, `slot_claim.py`) are untouched by the whole set, so guard behavior is identical pre- and post-revert.
- **05/04/03/01/08 reverts are clean deletions of additive files** (new models/services/`app/reward/`, `app/pipeline/spec/`, `app/core/cost_meter.py`) plus removing the one-line hooks. No data shape changes.
- **02's `run_id`/`pipeline_hash` fields on `PostCreationMetrics` are additive `None`.** Reverting drops them from *new* writes; existing TrackedPosts that carry them deserialize fine on old code too (extra keys are ignored by `model_validate`), so a revert is non-destructive even to data written while the feature was live.

### 5.2 Data rollback (the new collections are append-only and inert)

The set writes to **new** collections only: `PipelineSpecs`, `PipelineRevisions`, `OutcomeLedger`, `StepOutputs`, plus new fields on `AccountMetricsDocument` (`avg_post_reward`) and the `PipelineRuns` header (`step_links`). None of these are read by the pre-feature code, so **leaving them in place is safe** — they are orphaned, not corrupting. If a clean teardown is wanted:

```bash
# Optional: drop the new collections via RavenDB Studio or the HTTP API.
# They are inert under reverted code; deletion is hygiene, not correctness.
#   PipelineSpecs, PipelineRevisions, OutcomeLedger, StepOutputs
# The PipelineRuns.step_links / AccountMetrics.avg_post_reward fields are additive;
# exclude_none persistence means old code simply ignores them on read.
```

### 5.3 The champion/challenger promotion window (the one stateful seam)

04 §6c documents the only sequential-put hazard: promotion writes the new champion (PUT #1) then best-effort deletes the challenger. **Rollback of a bad promotion is itself a sequential put** — re-promote the previous champion by hash from the revision archive (04 §6c: `PipelineRevisionRepository.list_for_account` → the row whose `version_hash == new champion's parent_hash` → rebuild a `PipelineSpecDocument` from its `steps` → `repo.save`). No CAS needed; the rollback rides the same fail-safe ordering (a crash mid-rollback leaves the current champion live). **Default policy (04 §6c): manual promote, auto-rollback on hard regression** measured by 01's reward + 02's ledger.

### 5.4 Pre-flight snapshot (cheap insurance)

Before the first live force-post on the new path, snapshot the one account's derived state so any restore is faithful:
```bash
curl -s http://localhost:8000/api/accounts/JohnJames_News/edit > /tmp/jj_account_backup.json
# (the account doc itself is NOT mutated by this feature beyond the existing finalize_post writes;
#  this is belt-and-suspenders parity with soul-pipeline's rollback discipline)
```

> **Why rollback is low-risk here (Decision Defense):** unlike the soul refactor — whose first *save* dropped the `voice` sub-document and required a JSON snapshot to restore — the Interpreter adds new documents and additive `None` fields and **never rewrites the shape of an existing document**. The single behavioral switch (07's runner) is a pure code revert that re-exposes the still-present imperative path; the seed spec is a new doc the reverted code ignores. There is exactly one account, the new collections are inert under old code, and the only stateful operation (promotion) has a documented sequential-put rollback. The blast radius is a code revert plus an optional collection sweep.

---

## 6. Open questions

None blocking. The order is fixed (§2) and mirrored in `00-overview.md §4`, the import-break unit and its expected-RED window are named (§1, §4.A), every brief-named functional check maps to a concrete inspection and an owning doc (§4.B), and rollback is a code revert + inert-collection sweep with one documented promotion-rollback path (§5). This doc *places* rather than authors the internal DoD of docs 09–14, which it sequences and gates globally. Every slice is owned: the **backend read-route slice** is **doc 14 (CC-11)** — this doc pins its contract in §0.1 and sequences it as §2 step 9 (after the 06→07 unit, before doc 11). The builder *backend* is owned by doc 10 (`POST /api/agent-builder/chat`, **CC-10**); doc 11's frontend consumes that contract, not a parallel one.

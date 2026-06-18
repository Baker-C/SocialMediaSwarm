# Doc 07 — Interpreter Wiring (the runner becomes a spec walker)

> **Status:** Ready to implement. Authored in a planning session; pick up cold from this folder.
> **Scope:** Backend only. `app/interval/runner.py` (`_run_account_pipeline`), `app/pipeline/_runbook_engine.py` (`run_steps` gains engine-injected wrappers), one NEW file `app/core/cost_meter.py`, and the collapse of `app/interval/reference_phase.py` into the seed spec's SENSE steps.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB, in-process APScheduler threadpool).
> **Stays synchronous.** Everything in this doc runs in the current APScheduler worker thread — no `async`, no event loop, no reconcile poll. The compiled spec is walked top-to-bottom in one `run_steps` call.

---

## 0. Where this doc sits in the set

This is the **integration seam** of the Interpreter. It does not define new tools (06), the spec document (04), the compiler/validator (05), or the trace document (08) — those are the siblings. It rewires the **one place** that currently hand-codes the DECIDE→ACT tail (`_run_account_pipeline`) so that the WHOLE graph (SENSE + ACT) is one compiled spec walked by `run_steps`, and it adds the two **non-bypassable invariant wrappers** (cost meter + guardian) to the engine.

> **Canonical-shape note (reconciled with sibling 06 + sequencing doc 13).** Sibling 06 owns the two ACT tools, the `PostRunDeps` extension, and the `ArtifactKey.PUBLISHED_POST` artifact; it lands **before** this doc (13 §2 sequences `06 → 07` as one atomic import-break unit). This doc is the **authoritative runner shape**: ONE `run_steps(graph, …)` walk over the compiled spec (SENSE + ACT), driving 06's tools through 06's `compose_step`/`publish_step` wrappers. Where 06 §7.3 sketches an *imperative* two-step drive on `run_reference_phase` + `ReferencePhaseResult`, **this doc supersedes it**: `reference_phase.py` is deleted (§5), there is no `ReferencePhaseResult`, and the runner builds one `TickRunContext` and walks the whole graph. 06's tool *bodies* are reused verbatim; only 06's runner-drive sketch is replaced by §2.4 here.

| I depend on (defined elsewhere) | Sibling | What I consume |
|---|---|---|
| `PipelineSpecDocument` + `PipelineSpecRepository.load_or_default(account_id)` + `default_pipeline_spec(account_id)` | **04 (spec model)** | The per-account spec doc (champion, or baseline if none) loaded once per run |
| `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` + `validate_spec(doc, catalog) -> ValidationReport` | **05 (compiler/validator)** | Turns spec data into the existing `Step` graph; separates engine-injected deps from proposable config |
| `compose_until_safe` + `publish_post` catalog tools, the one-field `PostRunDeps` extension (`live: ActLive`, with `guardian`/`max_regeneration_rounds`/`bypass_post_cooldown` carried ON `ActLive` per CC-7), the 3 ACT `ArtifactKey`s, and their `services/steps.py` wrappers | **06 (ACT tail tools)** | The coarse compose-loop tool and the publish tool the ACT steps call |
| The seed spec (the SENSE steps + compose + publish, as data) via `default_pipeline_spec(account_id)` | **04 + 06 (seed spec)** | The default graph; replaces `POST_TICK_REFERENCE_STEPS` + the imperative tail. **04 seeds the 8 SENSE leaves; 06 appends the two ACT leaves to the seed (see §2.4 note).** |
| `StepOutputDocument` + the in-process trace sink | **08 (trace persistence)** | Full-fidelity per-step trace, written by an engine sink even when NATS is off |
| `PipelineSpecDocument.version_hash` (the `pipeline_hash`) + `PostCreationMetrics.run_id/pipeline_hash` | **04, 02 (attribution)** | The attribution join fields I thread through `finalize_post`. **`pipeline_hash` is the loaded spec's `version_hash` (04), NOT an account accessor (§7).** |

> I define exactly **one** new shared type: `CostMeter` (`app/core/cost_meter.py`, §4). Sibling 06's `compose_until_safe` reports per-leaf spend into it (§4.1); this doc owns its construction and injection.

---

## 1. Task Overview

| File | CHANGED / NEW / REUSED | Role (one line) |
|---|---|---|
| `app/pipeline/_runbook_engine.py` | **CHANGED** | `run_steps` gains an optional `wrappers` param; each leaf `step.run` is wrapped by cost-meter + guardian invariants before execution (§3). |
| `app/core/cost_meter.py` | **NEW** | `CostMeter` — per-run hard cost ceiling; raises `CostCeilingExceeded` before a leaf runs if the run is over budget (§4). |
| `app/interval/runner.py` (`_run_account_pipeline`) | **CHANGED** | Gains a `run_id` param (§6); load spec → `validate_spec(spec, catalog)` ONCE → `compile_spec(spec, catalog=catalog)` → build one `TickRunContext` → run the WHOLE graph via `run_steps`; the imperative compose/guardian/publish tail is deleted (§2). |
| `app/interval/runner.py` (`run_account_pipeline`) | **CHANGED (call only)** | The `run_events(...)` wrapper + `run_id` minting (`runner.py:141`) stay; the call site passes `run_id=run_id` into `_run_account_pipeline` (§2.4, §6) — same one-line change sibling 02 §3.2 makes. |
| `app/interval/reference_phase.py` | **DELETED** | Its work (build `TickRunContext`, run the SENSE runbook, extract artifacts) is now just "the first N steps of the compiled spec." Its SENSE steps live in the seed spec (`default_pipeline_spec`, sibling 04); helpers move per §5; the new runner body (§2.4) replaces it. |
| `app/interval/run_deps.py` | **NEW** | The pinned home for `post_run_deps_from_tick` (moved verbatim out of the deleted `reference_phase.py`, §5). The runner imports `post_run_deps_from_tick` from here; tests that build a bare `PostRunDeps` import it here too. |
| `app/interval/orchestration/slot_claim.py` | **REUSED (unchanged)** | Slot reserve/finalize/release still called from the runner around the spec walk (§2.2). |
| `app/interval/orchestration/post_guard.py` | **REUSED (unchanged)** | `try_begin_post` / `release_post_pipeline_guards` still bracket the run (§2.2). |
| `app/interval/orchestration/post_tick.py` (`finalize_post`) | **REUSED (unchanged here)** | `publish_post` (sibling 06) calls into the same `finalize_post` with the `creation_metrics` it built; `finalize_post` already forwards `creation_metrics` to `record_post` verbatim (`post_tick.py:59–65`) — no edit needed in this doc (the `run_id`/`pipeline_hash` are set on the metrics object by `publish_post`, §7; sibling 02 §4.3 adds the ledger stamp in this same function, but that is 02's edit). |
| `app/infrastructure/claude_client.py` | **CHANGED** | One line in `messages` records `msg.usage` into a per-run cost accumulator; adds `drain_run_llm_cost_usd()` for the cost wrapper (§4.1). |
| `app/pipeline/runbook.py` (`start`) | **REUSED** | Still the `TickRunContext` factory (`runbook.py:9`); called once in the new runner body (§2.4). |
| `app/pipeline/runbooks/post_tick.py` (`POST_TICK_REFERENCE_STEPS`) | **DELETED (moved)** | The SENSE tuple becomes the SENSE portion of the seed spec (sibling 04's `spec_from_runbook`). The frontend-sync warning header moves with it. (Sibling 06 appends the two ACT `Step`s here first; 04's seed then reads the full 10-leaf runbook — see §2.4 note on the 04+06 seed handoff.) |

**What it affects:** the live per-account post path on every scheduled tick and every force-post. After this doc, there is exactly one execution path: `_run_account_pipeline` compiles the account's spec and walks it; the guardian and the cost ceiling are enforced by the engine, not by spec content.

---

## 2. The new `_run_account_pipeline`

### 2.1 What it is today (verified against `runner.py:162–443`)

Today the function is a long imperative body:
1. `reload_account` + skip checks + `try_begin_post` + `try_reserve_interval_slot` (lines 173–218).
2. `run_reference_phase(ctx, account, copied_exclude=...)` → `ReferencePhaseResult` (line 228) — this is the ONLY part that touches the typed engine.
3. **Hand-written ACT tail** (lines 296–382): outer loop over `ranked_refs`, inner loop over `range(ctx.max_regeneration_rounds)`, `compose_formatted_post(...)` (line 322), `ctx.guardian.evaluate(...)` (line 340), `is_niche_mismatch_reject(...)` (line 354).
4. Build `PostCreationMetrics` (line 412) + `finalize_post(...)` (line 426).
5. `finally: release_post_pipeline_guards(ctx, aid)` (line 443).

Steps 2–4 are what becomes data. Steps 1 and 5 (locks/guards) stay imperative in the runner — they are **infrastructure around** the run, not part of the post-generation graph.

### 2.2 What stays imperative (locks, guards, skips)

These are NOT spec steps. They protect against double-posting and concurrent ticks; they must run before any spec work and must be released in a `finally`. Keep them verbatim:

- `reload_account` + `should_skip_account` + the `already_posted_this_interval` check (`runner.py:173–197`).
- `try_begin_post(ctx, aid, account)` (`runner.py:200`).
- `try_reserve_interval_slot(ctx, aid)` (`runner.py:209`) → `account = reservation.account`.
- `release_post_pipeline_guards(ctx, aid)` in the `finally` (`runner.py:443`).

> **Decision Defense — why locks stay out of the spec.** The slot/file/RavenDB locks (`slot_claim.py`, `post_guard.py`) are PID-keyed, threadpool-level, and non-serializable. They are an idempotency boundary, not a transformation of artifacts. Modeling them as `Step`s would require the engine to own lock lifecycle and rollback — pure complexity for zero data flexibility (the builder must never be able to remove a lock). They belong exactly where they are: imperative brackets in the runner. The spec walk happens strictly *inside* the acquired guards.

### 2.3 What becomes the spec walk

Everything from "we have a reserved slot" to "the post is published" is now **one compiled graph**. The compiled `Step` tuple (from `compile_spec(spec, catalog=catalog)`, sibling 05) is:

```
SENSE  (was POST_TICK_REFERENCE_STEPS — sibling 04 moves it verbatim):
  load_account_bundle → fetch_search_references → collect_external_references
  → fetch_own_post_history → summarize_for_compose (parallel: external + own briefs)
ACT    (new coarse steps — sibling 06 defines the tools + artifacts):
  compose_until_safe   reads: TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS, TIMELINE_RANKED
                         (the two briefs + the ranked pool the tool reads to build its
                         internal ranked_refs; the non-serializable loop inputs still
                         arrive via deps.live — see §2.3 note)
                       writes: COMPOSED_POST, SAFETY_VERDICT
  publish_post         reads: COMPOSED_POST, SAFETY_VERDICT
                       writes: PUBLISHED_POST
```

`compose_until_safe` owns the irreducible outer-ref/inner-regen loop internally (the loop body from `runner.py:304–365`), so the graph stays data at the meaningful grain. `publish_post` calls the same `finalize_post` that runs today, carrying an idempotency marker (sibling 06).

> **Declared compose `reads` (authoritative — graded by sibling 05's R3; tuple OWNED by sibling 06 §7.1).** `compose_until_safe`'s declared `reads` are exactly `(TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS, TIMELINE_RANKED)` — **matching sibling 06 §7.1's Step declaration and its `TOOL_READS` verbatim** (06 §7.1's note explicitly resolves the earlier 2-vs-3 divergence in favor of these THREE and requires 07 list the same three; this doc now does). `TIMELINE_RANKED` IS a declared read because the tool reads that artifact to build its internal `ranked_refs` (§5, sibling 06 §5.1) — it is a real upstream dependency (written by `rank_external_references`), so R3 passes and the mermaid edge "compose depends on the ranked pool" is honest. The non-serializable loop inputs (`reference_context_block`, `reference_pool`, `refs_payload`, and the resolved `ranked_refs` objects) still arrive via `deps.live` (sibling 06 §4.2), NOT as artifact reads — declaring `TIMELINE_RANKED` covers only the *serializable* ranked pool the tool re-reads. The seed (04+06) must carry `reads=(TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS, TIMELINE_RANKED)` so 05's R3 (dangling-read) grades against the one authoritative tuple. **Note:** sibling 04 §7's `ACT_TAIL_SPECS` currently seeds compose with only the two briefs — that seed must be updated to the three-read tuple to match 06 §7.1 (flagged for the 04 author; this is the canonical set).

> The three new `ArtifactKey`s (`COMPOSED_POST`, `SAFETY_VERDICT`, `PUBLISHED_POST`) and their Pydantic models are added to `app/pipeline/types/artifacts.py` by sibling **06** (§3), not here. This doc only relies on them existing so the ACT steps validate. **The terminal publish artifact is `PUBLISHED_POST` (model `PublishedPost`), matching 06 §3 and 05's R6/R7 terminal-write check — there is no `PUBLISH_RESULT` key.**

### 2.4 The full replacement body

`_run_account_pipeline` shrinks to: guards → load+validate+compile spec ONCE → build one context → `run_steps` the whole graph → map the terminal artifacts to the legacy return dict. Concretely:

> **The loaded spec MUST contain the two ACT leaves, or `validate_spec` rejects it (05 R6/R7).** The seed that `load_or_default` returns must end with `compose_until_safe` (writes `SAFETY_VERDICT`) + `publish_post` (writes `PUBLISHED_POST`), or 05's terminal-publish / safety-invariant checks fail and this runner returns `{"error": "invalid_spec:..."}` on every tick. **Handoff (04 + 06):** sibling 06 §7.1 appends the two ACT `Step`s to `POST_TICK_REFERENCE_STEPS`, and 06 must add their entries to sibling 04's seed `STEP_TOOL_MAP` (`compose_until_safe → llm.compose_until_safe`, `publish_post → data.publish_post`) so `spec_from_runbook` walks all 10 leaves. Since 06 lands before 07 (13 §2), the seed `default_pipeline_spec(account_id)` already yields the 10-leaf, ACT-terminated spec by the time this runner loads it. This doc does not author the seed; it requires the 04+06 handoff produce a spec that passes 05 — flagged so the implementer wires `STEP_TOOL_MAP` (06's edit to 04's seed) before relying on `load_or_default` here.

`_run_account_pipeline` gains a `run_id` parameter (threaded from the public `run_account_pipeline`, which already mints it at `runner.py:141` — sibling 02 §3.2 makes the same signature change; do it once here). The body becomes:

```python
# AFTER (app/interval/runner.py) — guards unchanged (§2.2), tail replaced.
# Signature gains run_id (minted in run_account_pipeline at runner.py:141; see §6).
def _run_account_pipeline(ctx: TickContext, account: AccountDocument, *, run_id: str) -> dict[str, Any]:
    aid = account.account_id
    outcomes = PipelineOutcomeRepository()

    # --- guards (verbatim from today, lines 173–218) ---------------------
    _orch_active("load_account")
    fresh = reload_account(ctx, aid)
    if fresh is None: ...   # unchanged skip handling
    account = fresh
    skip = should_skip_account(ctx, account)
    if skip: ...            # unchanged
    if ctx.mode == "scheduled" and account.last_interval_slot == ctx.slot: ...  # unchanged
    _orch_done("load_account")

    _orch_active("post_lock")
    _, guard_skip = try_begin_post(ctx, aid, account)
    if guard_skip: ...      # unchanged
    try:
        reservation, reserve_skip = try_reserve_interval_slot(ctx, aid)
        if reserve_skip: ...  # unchanged
        assert reservation is not None
        account = reservation.account
        _orch_done("post_lock")

        # --- load + validate + compile the account's pipeline ONCE -------
        spec = PipelineSpecRepository().load_or_default(aid)   # sibling 04
        catalog = get_tool_catalog()                          # sibling 03 (see §2.4 note)
        report = validate_spec(spec, catalog)                 # sibling 05 -> ValidationReport
        if not report.ok:
            codes = report.codes()
            out = {"account_id": aid, "error": f"invalid_spec:{codes[0] if codes else 'unknown'}"}
            outcomes.append(account_id=aid, phase="runner", status="error",
                            reason="invalid_spec",
                            details={"errors": [e.model_dump() for e in report.errors]})
            return out
        graph = compile_spec(spec, catalog=catalog)           # sibling 05 -> tuple[Step, ...]

        # --- one context for the WHOLE graph -----------------------------
        run_ctx = start(aid, niche=account.category, mode=ctx.mode, slot=ctx.slot)
        run_ctx.run_id = run_id                                # §6 — passed in, == current_run_id()
        deps = post_run_deps_from_tick(ctx)                   # the SAME live SENSE services (sibling 06 §4.3)
        deps.live = ActLive(                                  # CC-7 — ALL ACT handles/config live here, NOT on deps.*
            account=account,
            tick_ctx=ctx,
            guardian=ctx.guardian,                            # CC-7 — read by compose_until_safe off deps.live.guardian
            run_id=run_id,
            pipeline_hash=spec.version_hash,                  # CC-3/§7 — the loaded spec's version_hash (NOT an account field)
            copied_exclude=copied_reference_exclude_set(account),  # §5 (was runner.py:227)
            max_regeneration_rounds=ctx.max_regeneration_rounds,   # CC-7 — read by compose_until_safe off deps.live
            bypass_post_cooldown=ctx.bypass_post_cooldown,    # CC-7 — the bypass_* flag, engine-injected
        )

        # --- walk SENSE + ACT in one synchronous pass --------------------
        meter = CostMeter(run_id=run_id, ceiling_usd=settings.pipeline_cost_ceiling_usd)
        result = run_steps(
            graph, run_ctx, deps,
            wrappers=engine_invariants(meter=meter),
        )

        return _result_from_run(ctx, account, run_ctx, result, spec, outcomes)
    finally:
        release_post_pipeline_guards(ctx, aid)
```

> **`get_tool_catalog()` (sibling 05's helper).** Sibling 05's `validate_spec(doc, catalog)` and `compile_spec(doc, *, catalog=None)` take a catalog object exposing `.get(tool_id)` / `__contains__`. Sibling 03 builds it (`build_tool_catalog()` + the `ToolCatalog` wrapper class 03 adds for 05); 05 re-exports a module-default accessor `get_tool_catalog()`. Build it ONCE per run and pass the same object to both `validate_spec` and `compile_spec` so they grade against one catalog. (If 05/03 name the accessor differently, this is the single call site to update.)

> **`ActLive.followers_at_post` timing (resolved — read from the bundle, not `ActLive`).** `followers_at_post` is `profile.followers_count` from the account bundle, which the SENSE `load_account_bundle` step produces — it is NOT known before the walk, so it cannot be set when the runner builds `ActLive` (the construction above happens *before* `run_steps`). **Decision (the simpler option):** `ActLive` carries only pre-walk-known fields (per CC-7: `account`, `tick_ctx`, `guardian`, `run_id`, `pipeline_hash`, `copied_exclude`, `max_regeneration_rounds`, `bypass_post_cooldown`), and `publish_post` resolves `followers_at_post` at publish time from the `ACCOUNT_BUNDLE` artifact — `ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE)` → `bundle.profile.get("followers_count")` — exactly as the runner reads `bundle_account["profile"]["followers_count"]` today (`runner.py:249–253`), passing it into `finalize_post(..., followers_at_post=…)`. **Requirement on sibling 06's `publish_post`:** read `followers_at_post` from the bundle artifact, not from `deps.live` (06 §5.2's `live.followers_at_post` reference is replaced by this bundle read). This removes the pre-walk-timing problem entirely and keeps `ActLive` honest.

`post_run_deps_from_tick` is **moved out of the deleted `reference_phase.py` into `app/interval/run_deps.py`** (the pinned home — see the Decision Defense below; the runner imports it from there). It builds the SENSE-only `PostRunDeps` (`tick_data`/`repo`/`post_registry`/`twitter`); the ACT-injected handles (`guardian`/`max_regeneration_rounds`/`bypass_post_cooldown`) live on `deps.live` per **CC-7**, NOT as top-level `PostRunDeps` fields, so this doc populates them in the `ActLive(...)` construction above (where the account/run_id are in scope), not inside `post_run_deps_from_tick`. `ActLive` is sibling 06's dataclass (`app/pipeline/services/deps.py` or `act_types.py`).

> **Decision Defense — `run_deps.py` is the pinned home for `post_run_deps_from_tick` (resolving §1's "runner.py *or* run_deps.py").** Put it in a new `app/interval/run_deps.py`, not inline in `runner.py`. Two reasons: (1) `runner.py` already imports `post_run_deps_from_tick` *and* the deps-construction is reused by tests that build a `PostRunDeps` without driving the full runner — a standalone module keeps that import stable across the `reference_phase.py` deletion; (2) it keeps `runner.py` focused on the guards + spec-walk body and avoids re-introducing the helper sprawl the deleted `reference_phase.py` held. The §1 task table and §5's "new home" column are updated to name `app/interval/run_deps.py` (not "runner.py (or …)") so there is one answer.

### 2.5 Feeding the ACT steps their live services

The SENSE steps already get everything from `PostRunDeps` (`tick_data`, `repo`, `post_registry`, `twitter`). The ACT steps (`compose_until_safe`, `publish_post`) additionally need:
- the **account soul** (`posting_prompt`, `personality`, `contrast_patterns`, `punctuation_rules`, `category`) for `compose_formatted_post`,
- the **live `guardian`** for `evaluate`,
- the **`TickContext`** for `finalize_post` (which reads `ctx.twitter`, `ctx.post_registry`, `ctx.slot`, `ctx.now_iso`, and the locks),
- the **`copied_exclude` set** and the **`run_id`** for the compose-loop ranking and the publish idempotency/attribution.

**The `PostRunDeps` extension is sibling 06's, not this doc's — and per CC-7 it is EXACTLY ONE field.** Sibling 06 §4.1 adds **only** `live: ActLive | None = None` to `PostRunDeps` (optional/defaulted so the SENSE-only call sites and `PostRunDeps.build()` are unaffected). The ACT-injected config (`guardian`, `max_regeneration_rounds`, `bypass_post_cooldown`) lives on **`ActLive`**, NOT as top-level `PostRunDeps` fields — `compose_until_safe`/`publish_post` read them off `deps.live.guardian` / `deps.live.max_regeneration_rounds` (CC-7). This doc consumes that exact shape — it does **not** add `account`/`tick_ctx`/`guardian` directly on `PostRunDeps`; everything ACT-only travels on `deps.live` (the `ActLive` side-channel) so non-serializable handles never touch the artifact dict. The shape this doc relies on (defined by 06):

```python
@dataclass
class PostRunDeps:
    tick_data: TickDataService
    repo: AccountRepository
    post_registry: TrackedPostRepository | None = None
    pulled_tweets: PulledTweetRepository | None = None
    twitter: TwitterService | None = None
    # ── ACT-phase side-channel — the ONLY new field (CC-7; sibling 06 §4.1) ──
    live: "ActLive | None" = None        # carries guardian/max_regeneration_rounds/bypass_*/account/tick_ctx (06 §4.2)
```

`ActLive` (sibling 06 §4.2) carries the non-serializable handles + engine-injected config this doc's runner assembles, per CC-7: `account`, `tick_ctx`, `guardian`, `run_id`, `pipeline_hash`, `copied_exclude` (§5), `max_regeneration_rounds`, `bypass_post_cooldown`. The SENSE-derived `ranked_refs`/`reference_pool`/`refs_payload`/`reference_context_block` are **NOT** carried here — under this doc's **one-walk shape** there is no runner-side `ranked_refs` assembly: `compose_until_safe` derives them *internally* from the `TIMELINE_RANKED` artifact + `copied_exclude` (§5, sibling 06 §5.1). So `ActLive` carries only the pre-walk-known fields above — see §2.4's `ActLive(...)` construction and the `followers_at_post` note.

> **Decision Defense — why the soul/`tick_ctx`/`run_id` go on `deps.live`, not `TickRunContext.data`.** `TickRunContext.data` is the *artifact* dict — validated Pydantic models keyed by `ArtifactKey`, serialized for the trace (`context.py:45–52` `model_dump(mode="json")`). A live `AccountDocument`/`TickContext` cannot pass through `set_artifact` (it would drop the property accessors and the `finalize_post` mutation, and is non-serializable). `PostRunDeps` (and its `live` side-channel) is the per-run, engine-injected, **never-traced** home for live objects, matching the grounding that tool `run()` signatures take live service kwargs. This keeps the **injected vs. proposable** split honest: nothing on `PostRunDeps`/`ActLive` is LLM-tunable; only the spec's per-step config is.

### 2.6 Mapping the terminal artifacts back to the legacy return dict

Callers of `run_account_pipeline` (`run_interval_tick`, the force-post SSE worker) expect the dict shape `_run_status_from_out` reads (`runner.py:129–136`): `{"skipped": ...}` | `{"rejected": ...}` | `{"error": ...}` | a success dict with `tweet`. `_result_from_run` reads the terminal artifacts the ACT steps wrote and reconstructs that dict. **Live tests assert `'tweet' in out` (`test_orchestrator.py:109,165`)**, so the success branch MUST surface a `tweet` dict — see the note below.

```python
def _result_from_run(ctx, account, run_ctx, result, spec, outcomes) -> dict[str, Any]:
    aid = account.account_id
    # A SENSE step skipped (e.g. no reference with urls) -> skipped run.
    if not result.ok:
        reason = _first_failure_reason(result)            # from RunbookResult.steps log (see note)
        out = {"account_id": aid, "skipped": reason}
        outcomes.append(account_id=aid, phase="runner", status="skipped", reason=reason)
        return out
    verdict = run_ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)   # written by compose_until_safe
    if verdict is None or not verdict.approved:
        reason = (verdict.last_reject if verdict else None) or "all_compose_attempts_failed"
        out = {"account_id": aid, "rejected": reason,
               "references_tried": verdict.references_tried if verdict else 0}
        outcomes.append(account_id=aid, phase="runner", status="rejected", reason=reason)
        return out
    published = run_ctx.get_artifact(ArtifactKey.PUBLISHED_POST)  # written by publish_post (sibling 06 §3)
    if published is None or not published.posted:
        reason = (published.skipped_reason if published else None) or "publish_missing"
        out = {"account_id": aid, "error": reason}
        outcomes.append(account_id=aid, phase="runner", status="error", reason=reason)
        return out
    # CC-4 — return the FULL finalize_post dict carried on PublishedPost.result verbatim.
    # It already has the legacy shape {account_id, tweet:<full tw_result>, regeneration_round,
    # note?, creation_metrics?} (publish_post → finalize_post, post_tick.py:86–96), so the
    # COMPLETE `tweet` object survives — not a stripped {"id": ...}. `.result` is the canonical
    # carrier (sibling 06 §3.2); the flat fields exist only for the trace/dashboard.
    out = dict(published.result)              # 06 §3.2: result has {account_id, tweet, regeneration_round, …}
    outcomes.append(account_id=aid, phase="runner", status="ok")
    return out
```

> **Publish artifact = `PUBLISHED_POST` (model `PublishedPost`, sibling 06 §3.2).** Per **CC-4** the model carries a **`.result` field** (the FULL untruncated `finalize_post` dict) alongside the flat convenience fields (`account_id`, `tweet_id`, `posted`, `skipped_reason`, `regeneration_round`, `idempotency_key`, `note`). The runner returns `published.result` **verbatim** on the success path — it already has the legacy `{account_id, tweet, regeneration_round, …}` shape, so the complete `tweet` object survives and the `'tweet' in out` assertions in `test_orchestrator.py` hold against the real (full) tweet, not a reconstructed `{"id": …}`. The flat fields (`tweet_id`/`regeneration_round`/`posted`) are read only for the *classification* branches above (is-it-posted), never to rebuild the success dict. `SAFETY_VERDICT` (model `SafetyVerdict`, sibling 06 §3) has fields `approved: bool`, `last_reject: str | None`, `references_tried: int` — **not** `regeneration_round`; read `verdict.references_tried` for the rejected dict. The runner only reads these artifacts; it never constructs them.

> **`_first_failure_reason(result)`** is a small helper this doc adds in `runner.py`: it scans `RunbookResult.steps` (the per-leaf log list, `_runbook_engine.py:158–198`) for the first entry with `skipped`/`error` set and returns its `skip_reason`/`error`, falling back to `"reference_phase_failed"` (preserving today's `runner.py:230` skip reason string so the dashboard query is unchanged). A SENSE skip (e.g. no reference-with-urls) surfaces here as a `{"skipped": ...}` run, exactly as `run_reference_phase`'s `not ref.ok` branch does today (`runner.py:229–238`).

> `PipelineOutcomeRepository.append(...)` calls preserve the exact phase/status/reason strings (`"runner"` phase; `"skipped"`/`"rejected"`/`"ok"`/`"error"` status) the dashboard already queries (`runner.py:178,187,194,213,231,374,440`).

---

## 3. `run_steps` gains engine-injected invariant wrappers

The cost ceiling and the safety guardian are **non-bypassable**: they cannot be expressed or removed in a spec. The only correct place to enforce that is the engine, around every leaf, where spec content cannot reach. Today `run_steps` (`_runbook_engine.py:151–157`) calls `_run_step_with_progress(flat, ctx, deps)` at its single call site (`_runbook_engine.py:164`), which calls `step.run(ctx, deps)` (`_runbook_engine.py:65`). We interpose there.

> **Coordinate with sibling 08 (both edit `_run_step_with_progress`).** Sibling 08 (sequenced BEFORE this doc, 13 §2) adds a `record_step_trace(...)` call inside `_run_step_with_progress` (after the step runs, via a contextvar sink — it does NOT add a `wrappers` param). This doc adds the `wrappers` param + the `run_fn` wrapping. The two edits compose: 08's trace call records the **wrapped** result (what actually ran and what the cost/guardian wrappers saw), and a `CostCeilingExceeded` raised by the cost wrapper rides the existing `except Exception` path (§4.3) so 08's failure-path trace records it as `status="error"` like any other step exception. The combined final shape of `_run_step_with_progress`: build `run_fn` from `wrappers` (this doc) → `try: result = run_fn(ctx, deps)` → on success/skip/fail emit progress/events (unchanged) AND call `record_step_trace` (08) → return. Neither edit moves the timed `try`; this doc wraps *before* it, 08 records *inside/after* it.

### 3.1 Signature change (`_runbook_engine.py`)

`StepFn` (`Callable[[TickRunContext, PostRunDeps], StepResult]`) and `FlatStep` are already defined in `app/pipeline/types/flow.py` (`flow.py:14`, and `Step.run: StepFn` at `flow.py:23`) and `FlatStep` is already imported by `_runbook_engine.py:19` — import `StepFn` there too; add `Callable` from `collections.abc`.

```python
# A leaf wrapper sees the about-to-run step and returns a (possibly) wrapped run fn.
StepWrapper = Callable[[FlatStep, StepFn], StepFn]

def run_steps(
    steps: Sequence[Step],
    ctx: TickRunContext,
    deps: PostRunDeps,
    *,
    stop_on_fail: bool = True,
    wrappers: Sequence[StepWrapper] = (),     # NEW — engine-injected invariants
) -> RunbookResult:
    ...
    for flat in flat_steps:
        result, entry = _run_step_with_progress(flat, ctx, deps, wrappers=wrappers)
        ...
```

`_run_step_with_progress` applies the wrappers to `flat.step.run` exactly once, before the timed `try`:

```python
def _run_step_with_progress(flat, ctx, deps, *, wrappers=()):
    step = flat.step
    run_fn = step.run
    for wrap in wrappers:
        run_fn = wrap(flat, run_fn)          # outermost wrapper runs first
    ...
    try:
        result = run_fn(ctx, deps)           # was step.run(ctx, deps)
    except Exception as exc:
        ...
```

> **Decision Defense — wrapper list, not two hard-coded calls.** A `Sequence[StepWrapper]` keeps the engine ignorant of *what* the invariants are (cost, guardian, or a future audit hook) while still owning *that they run around every leaf*. The runner supplies the concrete list via `engine_invariants(...)`. Default `()` means every existing `run_steps` call site (SENSE-only tests, force-post) is unchanged and unwrapped — wrappers are opt-in per call, injected only by the live runner. This is the minimal change that satisfies "injected by the engine, never expressible in the spec."

### 3.2 `engine_invariants(...)` (lives in `runner.py`, the injection site)

```python
from app.infrastructure.claude_client import drain_run_llm_cost_usd   # §4.1

def engine_invariants(*, meter: CostMeter) -> tuple[StepWrapper, ...]:
    # No `guardian`/`niche` params: the guardian RUNS inside compose_until_safe via
    # deps.live.guardian (CC-7 — engine-injected on ActLive). The engine's guardian_wrapper
    # only ASSERTS the verdict artifact exists — it never re-invokes the guardian — so it needs neither.
    def cost_wrapper(flat, run_fn):
        def _run(ctx, deps):
            meter.check_before(flat.id)              # raises CostCeilingExceeded if over budget
            res = run_fn(ctx, deps)
            meter.record_after(flat.id, drain_run_llm_cost_usd())  # tally this leaf's LLM spend (§4.1)
            return res
        return _run
    # The guardian invariant is enforced INSIDE compose_until_safe (it owns the regen loop),
    # so the engine-level guardian wrapper is a NO-OP for SENSE steps and asserts the verdict
    # exists after the ACT compose step. See Decision Defense §3.3.
    def guardian_wrapper(flat, run_fn):
        def _run(ctx, deps):
            res = run_fn(ctx, deps)
            if flat.id == "compose_until_safe" and not ctx.has_artifact(ArtifactKey.SAFETY_VERDICT):
                raise RuntimeError("guardian invariant violated: compose wrote no SAFETY_VERDICT")
            return res
        return _run
    return (cost_wrapper, guardian_wrapper)
```

### 3.3 Where the guardian actually runs

The grounding is explicit and load-bearing: the guardian is woven into the **regeneration loop** — `compose_formatted_post` then `guardian.evaluate`, with the reject reason fed back into the next round (`runner.py:340–361`). That loop is irreducibly imperative and lives **inside** `compose_until_safe` (sibling 06). So the guardian's *real* enforcement is inside the ACT compose tool. The guardian reaches the tool via `deps.live.guardian` (CC-7 — engine-injected on `ActLive`, set by the runner's §2.4 construction), engine-injected and never proposable — a spec can tune `max_regeneration_rounds` but cannot null out the guardian.

> **Decision Defense — why a thin guardian wrapper at the engine, not a full guardian pass.** We cannot re-run the guardian as a separate engine step: it needs the per-attempt reject reason to steer regeneration, and a post-hoc engine check on the final body would lose that feedback (and could approve a body the loop already rejected for niche-mismatch). So `compose_until_safe` owns the guardian call and writes `SAFETY_VERDICT`. The engine wrapper's job is only to **guarantee the invariant held** — that an unsafe body cannot reach `publish_post`. It does that two ways: (1) it asserts `compose_until_safe` produced a `SAFETY_VERDICT` (a spec that swapped in a tool skipping the guardian would trip this — the wrapper keys on the bare top-level id `compose_until_safe`, which is correct because compose is a top-level step and `flatten_steps` yields a bare id for top-level leaves, verified `flow.py:103–113`), and (2) `publish_post` reads `SAFETY_VERDICT.approved` and refuses to publish a rejected body (sibling 06 §5.2). The cost meter is the wrapper that does real per-leaf work, because LLM spend accrues on *every* leaf, not just compose.

---

## 4. `CostMeter` — the hard cost ceiling (NEW: `app/core/cost_meter.py`)

A per-run tally with a hard ceiling, checked **before** each leaf runs so an over-budget run halts deterministically rather than after one more expensive LLM call.

```python
"""Per-run cost ceiling. Engine-injected, non-bypassable. Synchronous."""
from __future__ import annotations
from dataclasses import dataclass, field

class CostCeilingExceeded(RuntimeError):
    def __init__(self, run_id: str, spent: float, ceiling: float, step_id: str) -> None:
        super().__init__(f"cost ceiling {ceiling:.4f} exceeded ({spent:.4f}) before {step_id}")
        self.run_id, self.spent, self.ceiling, self.step_id = run_id, spent, ceiling, step_id

@dataclass
class CostMeter:
    run_id: str
    ceiling_usd: float
    spent_usd: float = 0.0
    per_step: dict[str, float] = field(default_factory=dict)

    def check_before(self, step_id: str) -> None:
        if self.ceiling_usd > 0 and self.spent_usd >= self.ceiling_usd:
            raise CostCeilingExceeded(self.run_id, self.spent_usd, self.ceiling_usd, step_id)

    def record_after(self, step_id: str, delta: float) -> None:
        # `delta` is the USD the leaf just spent, drained from ClaudeClient's per-run
        # accumulator by the cost wrapper (§4.1). 0.0 for non-LLM leaves.
        if delta:
            self.spent_usd += delta
            self.per_step[step_id] = self.per_step.get(step_id, 0.0) + delta
```

### 4.1 How spend is reported (concrete token source — closes the "dormant ceiling" gap)

The cost wrapper needs a USD delta per leaf. The honest problem the dry-run flagged: **`ClaudeClient.messages` (`claude_client.py:49–75`) returns only joined text and discards `msg.usage`**, so no tool has a token count to turn into a cost — an earlier sketch (each tool sets `ctx.data["_step_cost_usd"]`) silently never advanced because the coarse `compose_until_safe`/`reference_pattern_summary` never set it. We close the gap at the one place every LLM call already funnels through — `ClaudeClient` — rather than threading usage through every tool signature.

**(1) Make `ClaudeClient` accumulate token cost per run.** The anthropic SDK response carries `msg.usage.input_tokens` / `msg.usage.output_tokens` (verified: `client.messages.create(...)` is called at `claude_client.py:63`; `msg` is the SDK response and its `.usage` is populated). Add a tiny module-level accumulator and stamp into it after each call:

```python
# app/infrastructure/claude_client.py — add near the bottom.
import contextvars
from app.core.config import settings   # already imported at claude_client.py:10
# Per-run accumulated LLM cost in USD. The cost wrapper (cost_meter) reads + resets it.
_run_llm_cost_usd: contextvars.ContextVar[float] = contextvars.ContextVar("_run_llm_cost_usd", default=0.0)

def _tokens_to_usd(input_tokens: int, output_tokens: int) -> float:
    """tokens → USD via the ONE configurable blended rate (CC-9 — no hardcoded model price).
    `settings.cost_per_1k_tokens_usd` is a single USD-per-1K-tokens figure applied to
    total tokens; the ceiling is a runaway-loop guard, not a billing ledger, so a blended
    rate is sufficient and keeps the price out of code entirely."""
    total = (input_tokens or 0) + (output_tokens or 0)
    return total / 1000.0 * settings.cost_per_1k_tokens_usd

def _record_usage(usage) -> None:
    if usage is None:
        return
    cost = _tokens_to_usd(getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0))
    _run_llm_cost_usd.set(_run_llm_cost_usd.get() + cost)

def drain_run_llm_cost_usd() -> float:
    """Read and zero the accumulated LLM cost since the last drain. Called by the cost wrapper."""
    v = _run_llm_cost_usd.get()
    _run_llm_cost_usd.set(0.0)
    return v
```

In `messages` (after `msg = client.messages.create(...)`, `claude_client.py:63`), add one line: `_record_usage(getattr(msg, "usage", None))`. This is the only edit to the call path; `messages`/`messages_json_dict` keep returning text — no caller changes. (`settings` is already imported at `claude_client.py:10`, so no new top-level import is needed — the `from app.core.config import settings` line above is shown only for the standalone snippet.)

**(2) The cost wrapper drains the accumulator, not a tool-set key.** `record_after` no longer depends on each tool remembering to set `_step_cost_usd`; instead `cost_wrapper` (§3.2) calls `drain_run_llm_cost_usd()` after the leaf and tallies it:

```python
def record_after(self, step_id: str, delta: float) -> None:
    if delta:
        self.spent_usd += delta
        self.per_step[step_id] = self.per_step.get(step_id, 0.0) + delta
```

and the wrapper becomes `res = run_fn(...); meter.record_after(flat.id, drain_run_llm_cost_usd())`. Every leaf that issued any Claude call (`reference_pattern_summary`, and `compose_until_safe`'s internal `compose_formatted_post` + `guardian.evaluate` calls) is charged for exactly its tokens — including each regeneration round, because every round's `messages.create` accumulates. **The ceiling now trips on real spend**, not a synthetic value.

> **Decision Defense — drain a contextvar at `ClaudeClient`, not a `ctx.data` key set by tools.** The original sketch (a tool sets `ctx.data["_step_cost_usd"]`) required every present and future LLM tool to remember to compute and stash a number — exactly the silent-no-op the dry-run flagged (the coarse `compose_until_safe` and `reference_pattern_summary` never set it, so the meter never advanced). Funneling through `ClaudeClient` — the single chokepoint every LLM call already passes — makes cost reporting automatic and tamper-proof from spec content (a spec cannot route around the client). A `ContextVar` is correct because the run executes in one APScheduler worker thread/coroutine and the value must not leak across concurrent account runs. Per **CC-9** the price is a single configurable `settings.cost_per_1k_tokens_usd` blended rate — **no hardcoded model price in code**; pricing precision is not load-bearing (the ceiling is a *runaway-loop* guard, not a billing ledger). The `_step_cost_usd` key is dropped entirely.

### 4.2 Config

Add **two** fields to `app/core/config.py` (`Settings`), mirroring the existing `max_regeneration_rounds` / `pipeline_capture_payloads` defaults (`config.py:53,98`):

```python
# Per-run hard cost ceiling (USD). 0.0 disables enforcement (the `> 0` guard in CostMeter.check_before).
pipeline_cost_ceiling_usd: float = 0.50
# Blended LLM price in USD per 1K total tokens — the ONLY price in the system (CC-9; no hardcoded
# model price). _tokens_to_usd (claude_client.py) multiplies total tokens by this. Tune per model/plan.
cost_per_1k_tokens_usd: float = 0.009
```

The default `0.009` is a conservative blended figure (between typical input/output list rates); operators override it without touching code. `pipeline_cost_ceiling_usd = 0.0` disables the ceiling entirely.

### 4.3 What happens when the ceiling trips

`CostCeilingExceeded` propagates out of `run_fn` into `_run_step_with_progress`'s existing `except Exception` (`_runbook_engine.py:66`), which emits `step_failed` and returns a failed `StepResult`. `run_steps` then stops (`stop_on_fail=True`). `_result_from_run` sees `not result.ok` and returns a `skipped`/`error` dict — no post is published. The `finally` in the runner releases all guards. **No special handling needed**: the ceiling failure rides the engine's existing failure path. The trace records exactly which step was blocked.

---

## 5. Collapsing `reference_phase.py`

`reference_phase.py` exists only to (a) build a `TickRunContext`, (b) `run_steps(POST_TICK_REFERENCE_STEPS, ...)`, (c) extract artifacts from `run_ctx.data` into a `ReferencePhaseResult`, and (d) compute skip reasons. With the WHOLE graph now walked in one `run_steps` call, (a) and (b) move into the runner body (§2.4), the SENSE steps live in the seed spec (`default_pipeline_spec(account_id)`, sibling 04), and (c)/(d) dissolve — the ACT steps read the artifacts directly from the same `run_ctx`.

What must be preserved from the deleted file:

| Deleted helper (`reference_phase.py`) | New home | Why |
|---|---|---|
| `post_run_deps_from_tick(tick_ctx)` (lines 39–46) | **`app/interval/run_deps.py`** (pinned — §2.4 Decision Defense) | Still the way the live tick's services become the SENSE-only `PostRunDeps` (`tick_data`/`repo`/`post_registry`/`twitter`). The ACT-injected handles (`guardian`/`max_regeneration_rounds`/`bypass_post_cooldown`) are set on `deps.live` per **CC-7** by the runner's `ActLive(...)` construction (§2.4), NOT inside this helper. |
| `ranked_refs_from_runbook(...)` (lines 49–67) | `compose_until_safe` tool (sibling 06) | The outer-ref fallback list is the compose loop's input; it belongs to the tool that owns the loop. Inside the tool it reads `TIMELINE_RANKED` (artifact) + `deps.live.copied_exclude`, applies the `settings.max_reference_fallback_attempts` cap and the copied-exclude filter, and `GatheredTweet.model_validate`s the ranked rows — exactly as `ranked_refs_from_runbook` does today (sibling 06 §4.3 owns the transcription; this doc only fixes its *home* to the tool, not the runner). |
| `merge_reference_pool` / `filter_rows_with_urls` skip logic (lines 103–127) | SENSE step skip (already in the tools) | `rank_external_references` / `brief_external_references` already produce a skip when there's no reference-with-urls; the `RunbookResult.ok` path surfaces it (§2.6). The redundant re-derivation in `reference_phase.py` is dropped. |
| `ReferencePhaseResult` dataclass | **DELETED** | No longer needed; the runner reads artifacts from `run_ctx` directly. Sibling 06 §7.3's `run_ctx`-on-`ReferencePhaseResult` field is moot under this doc's one-walk shape — there is no `ReferencePhaseResult` to carry it. |

> **The `copied_exclude` thread (resolved).** `copied_reference_exclude_set(account)` (`runner.py:227`) is computed in the runner today and passed into `run_reference_phase`. It must now reach `compose_until_safe`. **Decision: carry it on `deps.live.copied_exclude` (the `ActLive` side-channel), NOT as spec config.** Rationale (the simpler, more elegant option): it is a live, per-run value derived from the account at run start — precisely what `ActLive` exists for — and routing it as spec config would collide with the unresolved "coarse ACT tools expose no config kwarg" problem (sibling 03/05: `compose_until_safe.run` takes only `(ctx, deps)`). `ActLive` already carries `account`; computing `copied_exclude` in the runner (`§2.4`) and reading it inside the tool keeps the injected-vs-proposable split honest (it is engine-injected, never LLM-tunable) with zero new config-binding machinery. **Add `copied_exclude: frozenset[str]` to `ActLive`** (sibling 06 §4.2) — this doc requires the field; 06 owns the dataclass.

**Tests touching the deleted module** must move, not break (full list; sibling 13 §1/§4.A also tracks these as the import-break unit's must-update set):
- `tests/test_reference_fallback.py` imports `ReferencePhaseResult` and patches `app.interval.runner.run_reference_phase` (lines 5, 92) → rewrite to assert on the compiled-graph result via the `SAFETY_VERDICT`/`PUBLISHED_POST` artifacts, or patch `compose_until_safe`.
- `tests/unit/test_reference_phase.py` imports `ranked_refs_from_runbook` (line 5) → move with the helper into the `compose_until_safe` test module.
- `tests/test_runner_post_guard.py` patches `run_reference_phase` (line 42) → patch the compose step or `run_steps` instead; the guard-release assertions (`finally`) are unchanged and must still pass.
- `tests/test_orchestrator.py` (the largest behavior-preservation suite) patches `app.interval.runner.compose_formatted_post` (line 151) and asserts `'tweet' in out` (165), `'tweet' in out['results'][0]` (109), `repo.load('a2').posts_total == 1` (110, 118). After the compose loop moves into `compose_until_safe`, patching `runner.compose_formatted_post` no longer affects execution (the call site moved into the tool). **Rewrite:** patch `app.pipeline.tools.llm.compose_until_safe.compose_formatted_post` (the new call site) instead of `app.interval.runner.compose_formatted_post`; the `'tweet' in out` / `posts_total == 1` assertions then hold because `_result_from_run` (§2.6) surfaces a `tweet` dict and `publish_post`→`finalize_post` still increments `posts_total`. This is RED until 06+07 land — it is part of the import-break unit, not a regression.
- `tests/unit/test_pipeline_runbook.py` asserts hard equality on `POST_TICK_REFERENCE_STEPS` flatten output: `test_runbook_step_names_are_readable` (line 18) and `test_runbook_top_level_step_ids` (line 32, 5 entries). Sibling 06 appends `compose_until_safe` + `publish_post`, so flatten yields 10 leaves / 7 top-level ids. **Update both assertions** to include the two ACT ids (sibling 06 owns the runbook append; the test update lands with the 06→07 unit). Listed here so the implementer expects this RED and does not mis-bisect.

---

## 6. Threading `run_id` through to the trace + ledger

`run_account_pipeline` already mints `run_id = ctx.forced_run_id or uuid4().hex` (`runner.py:141`) and binds it via `run_events(run_id=...)` (`runner.py:143–149`). Inside that context, `current_run_id()` (`dispatcher.py:90–92`) returns it — but typed `str | None` (it returns `None` outside a `run_events` block). The work here is to make the one canonical `run_id` reach the artifact trace and the attribution ledger:

1. **Thread it as a parameter (not a dispatcher read).** Change `_run_account_pipeline(ctx, account)` → `_run_account_pipeline(ctx, account, *, run_id)` and pass the wrapper's `run_id` at the call site (`runner.py:153`). This is the SAME signature change sibling 02 §3.2 makes (do it once, here, since this doc rewrites the whole function). The wrapper is the only place that knows the canonical id, so it hands it down — avoiding `current_run_id()`'s `Optional` return and guaranteeing the cost meter and the publish idempotency key (sibling 06) get a non-`None` stable value.
2. **Onto the context.** Add `run_id: str = ""` to `TickRunContext` (`app/pipeline/types/context.py:15–21` — currently has `account_id`/`slot`/`mode`/`niche`/`data` only) and set `run_ctx.run_id = run_id` right after `start(...)` (§2.4). The trace sink (sibling 08) reads `ctx.run_id` to key `StepOutputDocument` as `stepoutputs/{run_id}/{step_id}` and to link them from `PipelineRunDocument` (`pipelineruns/{run_id}`).
3. **Onto the cost meter.** `CostMeter(run_id=run_id, ...)` — so a `CostCeilingExceeded` names the run.
4. **Onto the post.** `publish_post`/`finalize_post` stamp `PostCreationMetrics.run_id = deps.live.run_id` and `.pipeline_hash = <loaded spec.version_hash>` (§7) so a posted tweet joins back to its run and its spec version.

> **Decision Defense — pass `run_id` down, and ALSO set it on `TickRunContext`.** Two consumers need it in two shapes: (a) the trace sink (08) reads `ctx.run_id` off the `TickRunContext` (it never sees the runner's locals), so the field must exist on the context; (b) the cost meter and `ActLive`/`publish_post` idempotency key need a guaranteed-non-`None` value at runner scope. `current_run_id()` returns `str | None`, so relying on it at the context-build seam risks a `None` slipping into the idempotency key. Threading the wrapper's already-minted `run_id` as a parameter (one signature, matching sibling 02) and copying it onto `run_ctx.run_id` keeps the dispatcher's id, the context's id, the cost meter's id, and the publish dedup key **identical by construction** — without depending on the `Optional` dispatcher read inside the hot path. `run_id == current_run_id()` still holds (both come from the wrapper's `run_id`), satisfying §8's DoD.

---

## 7. Attribution: `run_id` + `pipeline_hash` onto the posted tweet

This is the "one missing join field" from the grounding, threaded through the new path. `PostCreationMetrics` gains `run_id: str | None = None` and `pipeline_hash: str | None = None` — **sibling 02 §3.1 owns the model edit** (defaults `None` keep existing TrackedPosts valid). 02 is sequenced before this unit (13 §2: `… → 02 → 08 → 06 → 07`), so the fields exist by the time this doc stamps them; `PostCreationMetrics(run_id=…, pipeline_hash=…)` will not raise. The changes in *this* doc's territory are **where the values come from** and **who sets them** (the cross-doc gap: sibling 06 left these as a `# when 08 lands` placeholder, and 08 is the trace doc — so no doc actually sets them. This doc closes that):

- **`pipeline_hash` is the LOADED SPEC's `version_hash`, NOT an account accessor.** There is NO `account.pipeline_version_hash` on `AccountDocument` (verified `account.py:366–387`: only `voice_version_*` accessors exist; the spec lives in a separate `pipelinespecs/{account_id}` doc per sibling 04, never on the account). The runner loads `spec = PipelineSpecRepository().load_or_default(aid)` (§2.4); the value to stamp is `spec.version_hash`. Carry it into the ACT phase on **`deps.live.pipeline_hash`** (the runner sets it from `spec.version_hash` when building `ActLive` — add `pipeline_hash: str | None` to `ActLive`, sibling 06 §4.2). Do not read `account.pipeline_version_hash` anywhere — it does not exist, and inventing it would split the source of truth (04 deliberately keeps the hash off the account).
- Today `runner.py:412–424` builds `PostCreationMetrics` inline (voice fields already stamped). In the new flow, `compose_until_safe` knows the regen round / source ref and writes them into `COMPOSED_POST`; `publish_post` (sibling 06 §5.2) assembles the final `PostCreationMetrics`. **This doc's requirement on `publish_post` (overriding 06's placeholder):** it MUST set `run_id=deps.live.run_id` and `pipeline_hash=deps.live.pipeline_hash` explicitly (alongside the voice-version fields off `deps.live.account` — `account.voice_version_hash/seq/label`, as today at `runner.py:420–422`), then call `finalize_post(live.tick_ctx, account, body, …, creation_metrics=metrics, …)`. Replace 06's `# run_id / pipeline_hash: added in doc 08` comment with these two assignments. Without them, every posted tweet's `creation_metrics.run_id`/`pipeline_hash` is `None`, breaking 02's join, 09's champion/challenger scoring, and 13's B6 acceptance.
- `finalize_post` (`post_tick.py:23–96`) is otherwise **unchanged** — it already accepts `creation_metrics` and forwards it to `record_post` (`post_tick.py:59–65`). The grounding confirms `record_post(account_id, tweet_id, posted_at_iso, *, creation_metrics, followers_at_post)` (`post_registry.py:130–138`) stores it.

> The `publish_post` idempotency marker (so a retry can't double-post the non-idempotent `ctx.twitter.post_tweet`, `post_tick.py:36`) is sibling 06's responsibility (06 §5.2: a process-local ledger keyed `(run_id, account_id)`). This doc only requires that `run_id` is available to key it (it is — `deps.live.run_id`, threaded in §2.4).

---

## 8. Definition of Done (per slice)

**Engine wrappers (§3)**
- `run_steps(..., wrappers=())` default-path behavior is byte-identical to today: existing SENSE-only tests and the force-post path pass unchanged.
- With `wrappers=engine_invariants(...)`, every leaf's `run` is wrapped exactly once; a unit test asserts `cost_wrapper.check_before` is called before each `step.run` and `record_after` after.
- A spec whose `compose_until_safe` slot is swapped for a tool that writes no `SAFETY_VERDICT` makes the run fail with "guardian invariant violated" — proving the invariant is not bypassable from spec data.

**Cost meter (§4)**
- `CostMeter` unit test: 3 steps each reporting `0.2` with `ceiling_usd=0.5` → the 3rd `check_before` raises `CostCeilingExceeded`; `per_step` and `spent_usd` are exact.
- A run that trips the ceiling publishes nothing, releases all guards (`release_post_pipeline_guards` ran), and the trace shows the blocked step as `failed`.
- `ceiling_usd=0.0` disables enforcement (no raise regardless of spend).

**Runner rewrite (§2, §5, §6)**
- `_run_account_pipeline` body has no `for ref_idx ...` / `for reg_round ...` loops, no `compose_formatted_post` call, no `ctx.guardian.evaluate` call — those live in `compose_until_safe`. (grep the function body to confirm.)
- `reference_phase.py` is deleted; `post_run_deps_from_tick` and `ranked_refs_from_runbook` have moved (§5 table); no import of `app.interval.reference_phase` remains (`grep -r reference_phase app/`).
- One `run_steps` call walks SENSE+ACT; `run_ctx.run_id == run_id` (the wrapper's minted id, == `current_run_id()` inside the `run_events` block — identical by construction, §6).
- The legacy return dict is reconstructed: a happy-path scheduled tick returns the same `{account_id, tweet, regeneration_round, ...}` shape `run_interval_tick` collects, and `_run_status_from_out` classifies it `"ok"`.
- Slot-claim / cooldown / post-guard behavior is preserved: `tests/test_runner_post_guard.py` (guard release on failure) and `tests/test_reference_fallback.py` (rewritten per §5) pass. `tests/test_orchestrator.py` (re-patched per §5) passes: `'tweet' in out`, `posts_total == 1`.

**Attribution (§7)**
- A composed-and-published post yields a `TrackedPostDocument` whose `creation_metrics.run_id` equals the run's `run_id` and `creation_metrics.pipeline_hash` equals the loaded spec's `version_hash` (`PipelineSpecRepository().load_or_default(aid).version_hash`, NOT any account field); `voice_version_hash` is still stamped (unchanged). `publish_post` sets both explicitly (§7) — neither is `None` after a real post.

**Global**
- `python -m py_compile` clean across `runner.py`, `_runbook_engine.py`, `cost_meter.py`, `deps.py`, `context.py`, `config.py`, `claude_client.py`.
- `pytest` green for the runner/engine/reference suites (with the moved tests) — green only at the **close** of the 06→07 import-break unit, not mid-sequence (13 §1, §4.A "expected-RED window").
- `docker compose up -d --build` healthy; a force-post (`scripts/docker-forced-post.ps1` or Posts page) runs the spec end-to-end with NATS **off** and still writes the per-step trace (sibling 08's in-process sink) and publishes.

---

## 9. Open questions

None. Every decision above is resolved. The things this doc *relies on but does not define*, with the exact symbol it consumes and the owning sibling (final filename numbering):

- **Spec model + load + hash (04):** `PipelineSpecRepository().load_or_default(account_id) -> PipelineSpecDocument`; `default_pipeline_spec(account_id)` for the no-doc baseline; `spec.version_hash` is the `pipeline_hash` this doc stamps (NOT an account accessor — there is none).
- **Catalog (03):** `get_tool_catalog()` (and the `ToolCatalog` wrapper class 03 adds for 05) — built once per run and passed to both validator and compiler.
- **Validator + compiler (05):** `validate_spec(doc, catalog) -> ValidationReport` (with `.ok`/`.errors`/`.codes()`, a Pydantic object — NOT a list); `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` from `app/pipeline/spec/`.
- **ACT tools + deps + artifacts (06):** `compose_until_safe`/`publish_post` + their `compose_step`/`publish_step` wrappers; the one-field `PostRunDeps` extension `live: ActLive` (per CC-7 — `guardian`/`max_regeneration_rounds`/`bypass_post_cooldown` are carried ON `ActLive`, NOT as top-level `PostRunDeps` fields); the `ActLive` dataclass (this doc requires it carry `copied_exclude` and `pipeline_hash` alongside 06's `account`/`tick_ctx`/`guardian`/`run_id`/`max_regeneration_rounds`/`bypass_post_cooldown`); the three `ArtifactKey`s + models (`COMPOSED_POST`, `SAFETY_VERDICT`, `PUBLISHED_POST` — the terminal key is `PUBLISHED_POST` carrying a `PublishedPost` with a `.result` field per CC-4, matching 05's R6/R7; there is no `PUBLISH_RESULT`); the idempotency marker. **This doc overrides 06's `publish_post` placeholder by requiring it set `run_id`/`pipeline_hash` from `deps.live` (§7), reads the success result off `PublishedPost.result` (CC-4, §2.6), and supersedes 06 §7.3's imperative runner-drive sketch with the one-walk shape (§2.4).**
- **Attribution field (02):** the `run_id`/`pipeline_hash` fields on `PostCreationMetrics` (02 §3.1), sequenced before this unit so the stamping in §7 compiles.
- **Trace sink (08):** the in-process `StepTraceSink` + `record_step_trace` that reads `ctx.run_id`; this doc coordinates the shared edit to `_run_step_with_progress` (§3).

> **Sibling-number note:** an earlier draft of this doc referenced siblings by a provisional numbering (spec model "02", compiler "03", ACT tools "05", trace "06"). All cross-references above and throughout are now normalized to the final filenames: spec model = **04**, catalog = **03**, validator/compiler = **05**, ACT tools = **06**, attribution field = **02**, trace = **08**.

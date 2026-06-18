# PIPELINE — One Source of Truth

> Caveman doc. Short words. Big truth. This file replaces the old `00`–`14` docs
> (now in [`_archive/`](_archive/) — code comments still say "doc 05" etc., find them there).
> Everything about the tool + artifact + pipeline system lives HERE.

---

## 1. BIG IDEA

Pipeline = **data, not code**. A "spec" lists which tools run, in what order, with what knobs.
Engine reads spec, runs it. Same engine for everything.

Five rocks we stand on:
- **Tool** = small code, one job, declares what it reads/writes.
- **Artifact** = typed blob in a bag (`TickRunContext`). Only way steps talk.
- **Spec** = the pipeline as JSON (`PipelineSpecDocument`). One per account.
- **Catalog** = list of tools the spec is ALLOWED to use + which knobs it can turn.
- **Engine** = walks the spec, runs each step, traces every move.

Why: pipeline can rewrite itself (champion vs challenger), and every run is fully traced.

---

## 2. FOLDERS

```
backend/app/
  pipeline/
    tools/                 # THE TOOLS. one file = one tool.
      data/                #   touch outside world (X API, RavenDB)
      deterministic/       #   pure math. no I/O. no LLM.
      llm/                 #   call Claude
    types/
      artifacts.py         # all artifact models + ArtifactKey + ARTIFACTS registry
      context.py           # TickRunContext = the data bag (set_artifact/get_artifact)
      flow.py              # Step, chain(), parallel(), flatten_steps()
      tool.py              # StepResult (ok / skipped / payload / errors)
    spec/
      catalog.py           # introspect tools -> catalog. THE allow-list.
      validator.py         # R1..R7 rules. spec good or not.
      compiler.py          # spec JSON -> runnable Step tree
      internal_primitives.py  # built-in steps that are NOT catalog tools
    services/
      steps.py             # (ctx,deps) wrappers. glue tool <-> engine.
      deps.py              # PostRunDeps (services) + ActLive (live handles)
    runbooks/
      post_tick.py         # baseline post graph in code. MUST mirror the seed.
    events/                # trace + progress + capture (every step recorded)
    _runbook_engine.py     # run_steps(): walk graph, run step, trace, repeat
  models/
    pipeline_spec.py       # StepSpec / CompositeSpec / PipelineSpecDocument
    tool_catalog.py        # ToolCatalogDocument / ToolParameter
  interval/
    runner.py              # LIVE ENTRY. load -> validate -> compile -> run -> result
  services/
    pipeline_spec_repository.py  # load/save champion + challenger (RavenDB)
    spec_rewrite_service.py      # propose challenger spec (self-improve)
  scripts/
    seed_pipeline_spec.py        # build the baseline spec
```

---

## 3. WHAT EACH ROCK IS

### Tool ([`pipeline/tools/`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/tools))
One module. Has `run(ctx, ...)` + metadata constants:
- `TOOL_ID` — e.g. `"data.search_fetch"`. kind dot name.
- `TOOL_KIND` — `data` | `deterministic` | `llm`.
- `TOOL_SOURCE` (data) — `x_api` | `x_search` | `x_mentions` | `ravendb`.
- `PROMPT_STEM` (llm) — prompt name.
- `TOOL_READS` / `TOOL_WRITES` — artifact keys it eats / makes. (None = decided at runtime.)
- `OUTPUT_MODEL` — artifact model it makes.

Tool writes artifact with `ctx.set_artifact(KEY, payload)`. Validated on write.

### Artifact ([`types/artifacts.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/types/artifacts.py))
Typed Pydantic blob. Named by `ArtifactKey` enum. Stored as JSON in the bag.
`ARTIFACTS` table = key -> (model, purpose, producer). Read/write ONLY via
`ctx.set_artifact` / `ctx.get_artifact`. No raw dict smuggling.

### Spec ([`models/pipeline_spec.py`](../../../SocialMediaAutonomousAgents/backend/app/models/pipeline_spec.py))
- `StepSpec` = one leaf: `id`, `tool_id`, `reads`, `writes`, `config` (knobs), `purpose`.
- `CompositeSpec` = `parallel` or `chain` over children.
- `PipelineSpecDocument` = whole pipeline + `status` (champion/challenger) + `version_hash`.

### Catalog ([`spec/catalog.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/spec/catalog.py))
Reads tool `run()` signatures, builds the allow-list. Each param tagged:
- `injected` — live service (tick_data, repo, twitter…). never a knob.
- `runtime` — engine fills (account_id, slot, niche). never a knob.
- `wired` — wrapper computes (rows, store_key, winner…). never a knob.
- `literal` — **the only knobs a spec may set** (e.g. `top_n`, `max_results_per_query`).

### Wrapper ([`services/steps.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/services/steps.py))
Tool `run()` has many args. Engine only knows `(ctx, deps)`. Wrapper bridges:
pulls deps, pulls upstream artifacts, reads knobs from `ctx.data["_step_config:<tool>"]`,
calls the tool. One wrapper per runbook step.

### Engine ([`_runbook_engine.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/_runbook_engine.py))
`run_steps(graph, ctx, deps, wrappers=…)`. Flattens graph to leaves, runs each,
captures inputs/outputs, traces, stops on hard fail. Invariant wrappers (cost ceiling +
"compose MUST write safety_verdict") wrap every step.

### Deps ([`services/deps.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/services/deps.py))
- `PostRunDeps` = services every step may want (tick_data, repo, twitter…).
- `ActLive` = live non-serializable handles for ACT (guardian, account, run_id…).
  Rides on `deps.live`, NOT in the artifact bag. Built before the walk.

---

## 4. WORKFLOW

### Run lifecycle (LIVE, [`interval/runner.py`](../../../SocialMediaAutonomousAgents/backend/app/interval/runner.py))
```
interval_job -> Orchestrator -> run_interval_tick -> run_account_pipeline
   1. load spec      (champion or challenger; baseline if none)
   2. validate_spec  (R1..R7). BAD spec => stop. no post. no fallback.
   3. compile_spec   (spec JSON -> Step tree)
   4. run_steps      (walk SENSE then ACT, one context, traced)
   5. result         (map terminal artifact -> legacy return dict)
```

### Post pipeline graph (10 leaves)
```
load_account_bundle            -> account_bundle
fetch_search_references        -> search_references
collect_external_references    -> timeline_references   (_internal)
fetch_own_post_history         -> own_posts
parallel:
  chain: rank_external_references -> timeline_ranked
         brief_external_references -> timeline_analysis
  chain: rank_own_posts          -> own_posts_ranked
         brief_own_posts         -> own_posts_analysis
compose_until_safe   reads analyses+ranked -> composed_post + safety_verdict  (guardian loop inside)
publish_post         reads composed+verdict -> published_post                 (idempotent. TERMINAL.)
```
SENSE = gather + rank + summarize. ACT = compose + publish.

### Reply pipeline (separate family, `kind="reply"`)
```
fetch_mentions -> rank_mentions -> reply_compose -> reply_publish
mentions -> mentions_ranked -> reply_draft+reply_verdict -> reply_result
```

### Self-improve ([`spec_rewrite_service.py`](../../../SocialMediaAutonomousAgents/backend/app/services/spec_rewrite_service.py))
Clone champion. Bump a knob (or LLM rewrites it). Validate. If good + different => save as
challenger. Challenger runs in some slots; if it wins, `promote_challenger` makes it champion.

---

## 5. TOOLS (target = 10 catalog + 1 internal)

| tool_id | kind | source | reads | writes | family |
|---|---|---|---|---|---|
| `data.account_profile` | data | x_api | — | account_bundle | post |
| `data.search_fetch` | data | x_search | — | search_references | post |
| `data.own_posts_fetch` | data | ravendb | — | own_posts | post |
| `deterministic.reference_rank` | deterministic | — | dyn | dyn (store_key) | both |
| `llm.reference_pattern_summary` | llm | — | dyn | dyn (store_key) | post |
| `llm.compose_until_safe` | llm | — | timeline_analysis, own_posts_analysis, timeline_ranked | composed_post, safety_verdict | post |
| `data.publish_post` | data | x_api | composed_post, safety_verdict | published_post | post |
| `data.mentions_fetch` | data | x_mentions | — | mentions | reply |
| `llm.reply_compose` | llm | — | mentions_ranked | reply_draft, reply_verdict | reply |
| `data.reply_publish` | data | x_api | reply_draft, reply_verdict | reply_result | reply |
| `_internal.collect_external` | internal | — | search_references | timeline_references | post |

Artifacts (16 keys): account_bundle, search_references, timeline_references, own_posts,
timeline_ranked, own_posts_ranked, timeline_analysis, own_posts_analysis, composed_post,
safety_verdict, published_post, mentions, mentions_ranked, reply_draft, reply_verdict, reply_result.

Integrations (4 systems): **X API** (x_api/x_search/x_mentions/trends), **RavenDB**, **Claude LLM**, **Safety Guardian**.

---

## 6. ADD A NEW TOOL (the registration checklist)

Tool not real until ALL of these agree. Miss one = silent break.

1. **Write tool** in `pipeline/tools/<kind>/yourtool.py`. Set `TOOL_ID`, `TOOL_KIND`,
   `TOOL_READS`, `TOOL_WRITES`, `OUTPUT_MODEL`, `run(ctx, …)`.
2. **New artifact?** add `ArtifactKey` + model + `ARTIFACTS` entry in `types/artifacts.py`.
3. **Wrapper** in `services/steps.py`: `(ctx, deps) -> StepResult`. Wire deps + upstream
   artifacts. Read knobs from `ctx.data["_step_config:<tool_id>"]`. ← do this or knobs are dead.
4. **Catalog** `catalog.py`: add module to `_TOOL_MODULES`, add wrapper to `_TOOL_RUN`.
5. **Param tags** `catalog.py`: put each `run()` arg in `ENGINE_INJECTED_DEPS` /
   `RUNTIME_SUPPLIED` / `WIRED_FROM_CONTEXT`. Anything left = `literal` = a knob.
6. **Compiler** `compiler.py`: map step_id -> (tool_id, wrapper) in `_wrapper_by_step_id_entry`.
7. **Baseline?** add Step to `runbooks/post_tick.py` AND `STEP_TOOL_MAP`/`STEP_CONFIG` in
   `scripts/seed_pipeline_spec.py`. Keep the two identical.
8. **Test** baseline still validates against the REAL catalog:
   `validate_spec(spec_from_runbook(a), get_tool_catalog()).ok is True`.

> 8 places is too many. **Ideal:** catalog auto-discovers any module that declares `TOOL_ID`,
> and the wrapper is found by convention. Until then, this list is law.

---

## 7. VALIDATION RULES (R1..R7, [`validator.py`](../../../SocialMediaAutonomousAgents/backend/app/pipeline/spec/validator.py))

- **R1** every `tool_id` in catalog or is `_internal.*`.
- **R2** config keys are `literal` knobs + right type.
- **R3** read only artifacts some upstream step writes (or marked optional).
- **R4** no forward ref / cycle.
- **R5** step ids unique.
- **R6** exactly one terminal writer (`published_post` / `reply_result`), and it is LAST.
- **R7** some tool writes the verdict (`safety_verdict` / `reply_verdict`), and the terminal
  writer is a real catalog tool that statically declares the terminal write.
  → This is WHY compose + publish MUST be in the catalog.

---

## 8. RULES TO NOT BREAK

- **Catalog == executable tools.** Every tool the runbook runs is in `_TOOL_MODULES`.
  No dead entries, no missing entries. Else validate rejects and the live runner posts nothing.
- **Knobs must be honored.** If catalog says a param is `literal`, the wrapper MUST read it.
  Advertise-but-ignore = lie.
- **Declared reads/writes ≈ real reads/writes.** Engine does not enforce it; keep them honest
  or static checks (R3/R4) reason about a fake graph.
- **One execution path.** The spec-driven runner is the only path. No second hardcoded drive.
- **Tests use the REAL catalog.** No hand-built fixture catalog that hides drift.

---

## 9. FIX LIST (audit 2026-06; re-verified against HEAD on `2697feb`)

> **STATUS:** catalog fix + test cleanup (`a645cce` / `ec2888e` / `2697feb`) are now IN this
> branch. Each item below re-checked by running the real validator + full spec test suite
> (67 pass). **2 of 6 done; 4 open.**

1. ✅ **DONE — catalog has `compose_until_safe` + `publish_post`.** Baseline post spec validates
   (`ok=True`, 11 tools). Posting path restored. (`a645cce`)
2. 🟠 **OPEN — post knobs dead.** Post wrappers still ignore `_step_config`; only `mentions_fetch`
   / `rank_mentions` read it. `top_n` / `max_results_per_query` do nothing in the post family =>
   self-improve is a no-op. Fix per §6.3 (wrappers read the knob) or drop the knobs from catalog.
3. 🟡 **OPEN — dead/orphan tools.** `llm.compose_timeline_post` still in `_TOOL_MODULES`, mapped
   to `None` (never runs); `deterministic.reference_score` still wired nowhere. Remove both
   (then catalog == 10 live tools, matching §5).
4. ✅ **DONE — tests use the real catalog.** Suite green (67 pass). `test_pipeline_spec_seed` now
   validates the baseline against `get_tool_catalog()`; `test_tool_catalog` count fixed;
   `test_spec_rewrite_service` no longer crashes. (`ec2888e` / `2697feb`)
5. 🟡 **OPEN — `interval/reference_phase.py` still present.** Old doc 07 says delete it; it's a
   dormant 2nd path (only stale tests touch it). Delete + its tests.
6. 🟢 **OPEN — declared I/O incomplete.** `compose_until_safe` reads `timeline_references` and
   `publish_post` reads `account_bundle` without declaring them. Make declarations honest.

Target end-state: knobs honored (#2), dead tools gone so catalog == 10 (#3), one runner path
(#5), honest declared I/O (#6).

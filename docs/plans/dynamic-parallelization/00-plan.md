# Safe Dynamic Pipeline Parallelization — Final Implementation Plan

## Audit Provenance

This plan was authored against the **live code** (FastAPI + RavenDB backend under
`SocialMediaAutonomousAgents/backend/`) and then **adversarially verified**. Every file
path, line reference, and invariant below was checked against the actual source:

- `EventDispatcher._seq += 1` is **unlocked** (`app/pipeline/events/dispatcher.py:40,43`) —
  confirmed; must be parent-thread-only.
- `StepTraceSink._seq` is **unlocked** (`app/pipeline/events/step_trace.py:123,132`) —
  confirmed; must be parent-thread-only.
- `engine_invariants` returns `(cost_wrapper, guardian_wrapper)` as a flat tuple
  (`app/interval/runner.py:203-231`); `guardian_wrapper` triggers **only** on
  `flat.id == "compose_until_safe"`, which is always a forced singleton — so a concurrent
  unit carries effectively no guardian wrapper. Cost accounting must move to the parent.
- `_run_llm_cost_usd` is a `contextvars.ContextVar`
  (`app/infrastructure/claude_client.py:16-17`) — confirmed isolated per `copy_context()`.
- `_run_step_with_progress` (`app/pipeline/_runbook_engine.py:47-167`) interleaves
  `emit_step_*` / `record_step_trace` / `progress_*` with `run_fn(ctx, deps)` exactly as
  described; input capture is at `:62`, output capture at `:150`.
- Settings live in `app/core/config.py`, `class Settings`,
  `pipeline_cost_ceiling_usd: float = 0.50` at `:100`.
- Test layout is `backend/tests/unit/pipeline/` and `backend/tests/unit/` — confirmed.

**Landing guidance.** **Phase A is verified-sound and safe to land first** (pure
functions, additive default-`None` model fields, one new validator rule; the scheduler is
computed-but-unconsumed; zero behavioral change). **Phase B MUST include the
`_run_step_with_progress` split (B.0)** — splitting pure execution from side effects is the
linchpin that makes "workers execute only, the parent emits/traces/accounts single-threaded"
both achievable and byte-identical on the sequential path. The scheduler/independence
predicate, dotted-id stability, validator single-writer rule, and flag-off byte-identical
behavior are verified sound and are preserved as-is.

---

## 0. Goal & Non-Goals

**Goal.** Run pipeline steps as soon as their declared inputs are ready, and run independent steps within a wave concurrently, without changing any observable behavior until a feature flag is flipped. Concurrency is an *engine-level execution hint computed over the existing flat leaf list*: a pure scheduler turns `flatten_steps(steps) -> list[FlatStep]` into ordered waves of parallel-safe groups, and `run_steps` dispatches each group on a bounded thread pool. Leaf dotted ids (`FlatStep.id`) stay byte-identical, so `StepOutputDocument.step_id`, the frontend `flowGraph.ts` lock, and trace lineage are untouched. The single shared mutable surface — `ctx.data` — is never mutated concurrently: each child runs against its own seeded scratch context, and the parent merges results single-threaded.

**Non-Goals.** No `CompositeSpec` or compiler change (it would re-key every dotted id and break the `flowGraph.ts` lock + trace lineage). No async/await, no job queue, no distributed dispatch — a wave runs in-process on a `ThreadPoolExecutor` with the parent thread as the barrier. No new run-state store: `CostMeter`, `StepTraceSink._seq`/`_links`, `EventDispatcher._seq`, and `PipelineOutcomeRepository` stay the only state, and **every one of them is touched single-threaded on the parent thread**. No last-writer-wins merge (same-key writes raise). No mid-wave fail-fast (a started thread can't be cancelled — we collect-all-then-report with a per-child timeout). No change to `flow.parallel/chain`. Phase C is data-only on the read route; the hand-authored `flowGraph.ts` diagram is explicitly out of scope.

---

## 1. Architecture in one diagram-in-words

```
compile_spec(spec) ──► Step tree           (UNCHANGED — compiler.py, flow.parallel/chain)
        │
flatten_steps(steps) ──► list[FlatStep]     (UNCHANGED — declared order, dotted ids stable)
        │
plan_execution_units(flat) ──► list[list[str]]   (NEW pure fn — scheduler.py)
        │     waves peeled Kahn-style; each wave partitioned into parallel-safe GROUPS;
        │     guardian/terminal forced to singletons; output = ordered list of unit id-lists
        │
run_steps loop  (per unit, in order):
        │
        ├─ flag OFF  ──► existing sequential loop, byte-identical          (_runbook_engine.py)
        │
        └─ flag ON:
             len(unit)==1 ──► existing single-step path (byte-identical: _execute_step then
             │                _emit_and_trace_step on the parent)
             │
             len(unit)>1  ──► EXECUTE WAVE:
                   for each child:  child_ctx = seeded scratch ctx (reads only)
                                    ThreadPoolExecutor.submit(copy_context().run, _execute_step, child_ctx)
                   COLLECT-ALL  (per-child timeout → synthetic timeout result)
                   ────────── barrier ──────────
                   MERGE on parent, in unit order:   ctx.data[writes] ← child_ctx.data
                                                     same-key across children ⇒ RAISE
                   EMIT+TRACE on parent, in unit order: _emit_and_trace_step per child
                                                        (StepTraceSink._seq, EventDispatcher._seq,
                                                         CostMeter, outcomes — all parent-thread)
        ► next unit
```

The one structural change that makes concurrency *and* single-threaded state both hold: **split `_run_step_with_progress` into pure execution (runs on the worker) and side effects (run on the parent, in unit order).** Today that function interleaves `emit_step_*` / `record_step_trace` / `progress_*` with `run_fn(ctx, deps)` (`_runbook_engine.py:47-167`), so the trace/event side effects cannot be replayed without re-running the step. After the split, the worker produces a pure result + captured I/O struct, and the parent does all emitting/tracing serially.

---

## 2. Phase A — Pure Foundations (land first; sequential execution unchanged)

Everything here is a pure function, an additive default-`None` model field, or one new validator rule. The scheduler is *computed but not yet consumed* by `run_steps`. Trace/`FlatStep` fields stay `None` on the sequential path. **Zero behavioral change.**

### A.1 — Scheduler (pure)

| File | NEW/CHANGED | Change |
|---|---|---|
| `backend/app/pipeline/scheduler.py` | **NEW** | `plan_execution_units(flat_steps: list[FlatStep]) -> list[list[str]]` plus pure helpers `_independent`, `_build_deps`, and the `EXCLUDED_WRITES` constant. No imports of ctx/deps/ContextVars/I/O. |
| `backend/app/pipeline/types/flow.py` | unchanged | `flatten_steps` (`:103-114`) already yields leaves in declared order with dotted ids; the scheduler consumes its output as-is. |

Reads per leaf `i` off `FlatStep.step` (`flow.py:24-26`, all `tuple`/`frozenset[ArtifactKey]`):
- `W[i] = set(step.writes)`
- `R[i] = set(step.reads) | set(step.reads_optional)`
- `order[i] = i` (declared index — deterministic tiebreak)

`producers: dict[ArtifactKey, list[int]]` keeps the **full** writer list per key in declared order. `deps[i] = { p for r in R[i] for p in producers[r] if p < i }` — a reader waits for **every** prior producer of a key (fixes the audit's multi-writer defect where only the last writer was tracked). Declared order is topological by construction (validator `_check_no_cycles`, `validator.py:283-309`), so `p < i` is sufficient and no runtime cycle handling is needed. See A.1-pseudocode in §5.

**EXCLUDED set** (forced singletons, mirrors `guardian_wrapper` runner.py:222-229 and validator R6/R7):
```
EXCLUDED_WRITES = {SAFETY_VERDICT, REPLY_VERDICT, PUBLISHED_POST, REPLY_RESULT}
```

**Decision — `reads_optional` is folded into the independence predicate ONLY, not into `deps`.** The independence predicate uses `R = reads | reads_optional` so an optional consumer is never co-scheduled with its producer — this closes the race. But `deps` uses **`reads` only**, so a step is *not* force-serialized behind an optional producer that may be legitimately absent. The post spec (`post_tick.py`) has no `reads_optional` edges, so the heavier "hard edge in deps" rule constrained nothing real while complicating the dep builder; we take the lighter, equally-safe side. (Formally: keeping an optional pair out of the same wave is sufficient for safety; forcing a cross-wave order is not required.)

**DoD — A.1.** Tests in `backend/tests/unit/pipeline/test_scheduler.py` (pure, no sink/ctx):
- `plan_execution_units([]) == []`.
- Linear chain (A writes k, B reads k, C reads k') → three singleton units in declared order.
- Two independent leaves at same depth → **one** unit of length 2, ids sorted by declared index.
- **WAW guard:** two leaves writing the same key → **two** singletons (the racing case is *rejected* from grouping, not co-scheduled), even at equal depth.
- **WAR guard:** A writes k, B reads k at same depth → never grouped; B's unit strictly after A's.
- **Multi-writer RAW:** k written by leaves 0 and 1, read by leaf 2 → `deps[2] == {0,1}`; leaf 2 strictly after both.
- **`reads_optional`:** A writes k, B has `reads_optional={k}` → B is **not** in A's unit (predicate keeps them apart) but B is **not** force-serialized cross-wave if A is absent in a variant spec (asserts the lighter rule).
- **EXCLUDED:** any leaf writing a terminal/verdict key → always its own singleton, even if independent of wave-mates.
- **Determinism:** `plan(x) == plan(x)` across 100 calls.
- **Acyclic assumption:** a hand-built cyclic dep input trips the `assert wave` (documents the invariant).

### A.2 — Validator single-writer rule

| File | CHANGED | Change |
|---|---|---|
| `backend/app/pipeline/spec/validator.py` | Add `_check_single_writer(flat) -> list[ValidationError]` after `_check_no_cycles` (~`:310`); wire `errors += _check_single_writer(flat)` between R4 (`:478`) and R5 (`:479`). |

`flat` here is the spec-doc leaf list from `_flatten_spec_leaves` (`:130-141`), not engine `FlatStep`. `_step_writes(node)` is `:69-71`.

```python
def _check_single_writer(flat) -> list[ValidationError]:
    writers: dict[str, list[str]] = {}
    for dotted_id, node in flat:
        for w in _step_writes(node):
            writers.setdefault(w, []).append(dotted_id)
    return [
        ValidationError(code="multiple_writers", artifact=art, step_id=ids[-1],
                        detail=f"artifact {art} written by {len(ids)} steps: {ids}")
        for art, ids in writers.items() if len(ids) > 1
    ]
```

No model change — `ValidationError` already carries `code`/`artifact`/`step_id`/`detail` (`:22-28`). This is the static precondition that makes the Phase-B same-key merge RAISE unreachable in valid specs. **Surfaced caveat:** `_flatten_spec_leaves` discards composites, so this forbids *any* two leaves writing one key (it cannot distinguish sequential from cross-branch duplicate writers). That is exactly the safety precondition we want; allowing duplicate writers in sequence is out of scope.

**DoD — A.2.** Tests in `backend/tests/unit/pipeline/test_validator_single_writer.py`:
- Valid post spec → `report.ok is True`, `"multiple_writers" not in report.codes()`.
- Two non-terminal leaves writing the same artifact → `report.ok is False`, `"multiple_writers" in codes()`; `artifact` is the shared key, `step_id` the later writer.
- Single-terminal spec still passes R6/R7 and the new rule.
- Order-independent: shuffling declaration order flags the same artifact.

### A.3 — Additive trace/`FlatStep` fields + passthrough

| File | CHANGED | Change |
|---|---|---|
| `backend/app/models/step_output.py` | Add after `parent_id` (`:37`): `parallel_group: list[str] | None = None`, `branch_index: int | None = None`. |
| `backend/app/pipeline/types/flow.py` | Add the same two default-`None` fields to `FlatStep` (`:94-100`). `flatten_steps`/`_flatten_one` leave them default; the scheduler assigns membership at dispatch time (Phase B). |
| `backend/app/pipeline/events/step_trace.py` | In the `StepOutputDocument(...)` construction (`:76-92`), add `parallel_group=flat.parallel_group, branch_index=flat.branch_index,` right after `parent_id=flat.parent_id,` (`:81`). |

`parallel_group` = the unit's full id-list (which steps ran together); `branch_index` = 0-based position in that list (intra-group order; `seq` is meaningless inside a concurrent group). `FlatStep` is `frozen=True`, so Phase B constructs children via `dataclasses.replace(flat, parallel_group=…, branch_index=…)`. The two `record_step_trace` call sites already pass `flat`, so they need no change. The `_trace_sink is None → return` no-op guard (`step_trace.py:72-74`) is preserved.

**DoD — A.3.**
- `StepOutputDocument(run_id="r", account_id="a", step_id="s")` → both new fields `None`.
- Round-trip `model_validate(old_doc_dict)` (dict lacks the keys) → both `None` (additive, no migration).
- `record_step_trace` with a sink and a `FlatStep` carrying `parallel_group=["x","y"], branch_index=1` → doc has those values; with a plain `FlatStep` → both `None`.

### Phase A overall DoD
- `pytest backend/tests/unit/pipeline` green incl. the two new files.
- Flag absent/off → `run_steps` iterates `flat_steps` exactly as `_runbook_engine.py:182-218` today; the scheduler is computed but unconsumed. Confirmed by an unchanged golden trace on the reference spec.

---

## 3. Phase B — Concurrency (behind a default-off flag)

**Prerequisite refactor (B.0): split `_run_step_with_progress`.** This resolves the central tracing-path contradiction (one part said "trace on worker," another said "trace on parent" — mutually exclusive, and the parent path was unachievable without the split). The split makes the parent path achievable.

### B.0 — Split the step runner + add the flag

| File | CHANGED | Change |
|---|---|---|
| `backend/app/pipeline/_runbook_engine.py` | Split `_run_step_with_progress` into **`_execute_step(flat, ctx, deps, *, wrappers=()) -> StepExecution`** (PURE execution: applies wrappers, runs `run_fn(ctx, deps)`, returns a `StepExecution` struct of `result`, `captured_inputs`, `captured_outputs`, `started_iso`/`ended_iso`/`duration_ms`, `error_dict`, `status`, `entry`) and **`_emit_and_trace_step(flat, exec) -> entry`** (ALL side effects: `progress_*`, `emit_step_started/completed/failed/skipped`, `record_step_trace`, from that struct only — never re-reads ctx). The existing public `_run_step_with_progress(flat, ctx, deps, wrappers)` becomes `exec = _execute_step(...); _emit_and_trace_step(flat, exec); return exec.result, exec.entry` — **byte-identical for the sequential path.** |
| `backend/app/core/config.py` (`class Settings`, alongside `pipeline_cost_ceiling_usd` at `:100`) | Add **one** setting: `pipeline_parallel_enabled: bool = False`. (No `max_workers` / `step_timeout_s` config — `MAX_WORKERS = 4` and `STEP_TIMEOUT_S = 120.0` are module constants until concurrency is proven.) |

`_execute_step` must capture inputs/outputs *itself* against the child ctx. Today `emit_step_started` captures `inputs` (`:62`) and `emit_step_completed` captures `outputs` (`:150`) inline — these reads must happen on the worker against `child_ctx`, because the parent ctx is merged afterward and would trace the wrong artifact value (the exact failure mode the audit flagged). So the struct carries the captured I/O; `_emit_and_trace_step` only *emits* from the struct, never re-reads ctx.

**Note (capture vs. merge):** `record_step_trace`'s `capture_artifacts_full` must capture from the CHILD's scratch ctx (carried in the `StepExecution` struct), NOT the merged parent ctx — so a value later overwritten by merge still traces correctly.

**DoD — B.0.** With the flag off, `_run_step_with_progress` (now a 2-line composition) produces byte-identical `RunbookResult.steps` and an identical event sequence vs the pre-refactor build (golden test). Toggling the flag requires no spec change.

### B.1 — Wire scheduler + per-child scratch contexts + worker dispatch

| File | CHANGED | Change |
|---|---|---|
| `backend/app/pipeline/_runbook_engine.py` | In `run_steps`: after `flat_steps = flatten_steps(steps)`, if `not settings.pipeline_parallel_enabled` run the **existing loop unchanged**; else build `by_id = {f.id: f for f in flat_steps}`, `units = plan_execution_units(flat_steps)`, and loop per unit (see §6). Add `_run_wave` and `_make_child_ctx`. |
| `backend/app/pipeline/runbook.py` | unchanged | `start(...)` (`:9-22`) reused verbatim for scratch contexts. |

A length-1 unit goes through the existing single-step path (`_execute_step` then `_emit_and_trace_step` on the parent) — byte-identical, preserving `stop_on_fail`/outcomes/break semantics.

Per-child scratch context (canonical sibling pattern, runner.py:390-391):
```python
def _make_child_ctx(parent, flat):
    child = start(parent.account_id, niche=parent.niche, mode=parent.mode, slot=parent.slot)
    child.run_id = parent.run_id                         # start() leaves run_id=""
    keys = {k.value for k in (set(flat.step.reads) | set(flat.step.reads_optional))}
    child.data = {k: copy.deepcopy(parent.data[k]) for k in keys if k in parent.data}
    return child
```

`start()` gives a fresh empty `.data` (`context.py:22`). **The seed is a `deepcopy`, not a shallow copy (Q2b):** artifacts are JSON dicts, and a deepcopy guarantees a child that mutates a nested field of a seeded *read* value cannot share state by reference across siblings. (Cost is negligible: a handful of small JSON dicts per wave.) The alternative — documenting artifacts as immutable and forbidding in-place nested mutation of seeded reads — was rejected in favor of the deepcopy because it removes a footgun at negligible cost. **`mode` caveat:** `start()` coerces modes outside `{"scheduled","force"}` to `"scheduled"`; `TickRunContext.mode` is already that `Literal`, so this is a no-op for valid parents.

**DoD — B.1.**
- Flag on, a unit of two independent leaves: each child writes only into its own `child.data`; the parent `ctx.data` is **unchanged** until the merge (B.2) runs (asserted directly).
- Each child runs through `_execute_step` on its worker; the returned struct carries that child's captured inputs/outputs read against `child_ctx`.

### B.2 — Collect-all barrier (timeout) → parent-thread merge / emit / trace / cost

| File | CHANGED | Change |
|---|---|---|
| `backend/app/pipeline/_runbook_engine.py` | `_run_wave`: submit children under `copy_context()`, collect with `future.result(timeout=STEP_TIMEOUT_S)`, then on the parent in unit order: merge `child_ctx.data` (raise on same-key), call `_emit_and_trace_step` per child, sum LLM cost, append outcomes. |

**Single chosen tracing path (the central resolution).** Workers run **`_execute_step` only** — they emit and trace **nothing**. All `emit_step_*` (which bump `EventDispatcher._seq`, dispatcher.py:43) and all `record_step_trace`/`StepLink` (which bump `StepTraceSink._seq`, step_trace.py:132) happen in `_emit_and_trace_step`, called by the parent in `sorted(unit)` order after the barrier. This is achievable precisely because of the B.0 split. Consequences:
- `EventDispatcher._seq` (dispatcher.py:40,43) **and** `StepTraceSink._seq` are mutated **only** on the parent thread → no race. **Both** run-scoped sequence counters are explicitly in scope here (Q4a).
- `seq` reflects unit emission order; `branch_index` carries the authoritative intra-group order. Two runs of one spec produce identical `(step_id, seq, branch_index)` triples.
- Captured I/O is correct: `_execute_step` captured outputs against `child_ctx` *before* the merge, so a step's traced outputs are its own writes, not a merged/overwritten value.

**Worker wrappers (cost/guardian split, concretely — Q4b).** `engine_invariants` returns `(cost_wrapper, guardian_wrapper)` (runner.py:203-231). For a concurrent unit:
- **`guardian_wrapper`** fires only on `flat.id == "compose_until_safe"` (runner.py:225), which writes `SAFETY_VERDICT` and is therefore in `EXCLUDED_WRITES` → **always a forced singleton, never inside a multi-step unit.** So concurrent units carry **effectively no guardian wrapper**. Children therefore run with **no wrappers**.
- **`cost_wrapper`** does `meter.check_before(id)` then `meter.record_after(id, drain_run_llm_cost_usd())` (runner.py:213-220). Because each worker runs under its own `copy_context()`, `_run_llm_cost_usd` (a ContextVar, `infrastructure/claude_client.py:16-17`) is **isolated per child**: the worker drains its own and returns the float. On the parent, after the barrier, in `sorted(unit)` order: `meter.check_before(id)` then `meter.record_after(id, child_cost_float)` per child.
- **Ceiling timing (accepted behavior change, stated explicitly).** `CostMeter.check_before` for a concurrent unit fires **on the parent, per child, in unit order, after the barrier** — i.e. the ceiling check moves from "before each leaf executes" to "before the wave is accounted." For a wave whose summed cost crosses the ceiling, `CostCeilingExceeded` is raised by the first child (in unit order) whose pre-check trips it; **this can change which step a `CostCeilingExceeded` names** vs the sequential path. All children in a wave will already have executed when the ceiling fires. This is accepted because waves are 2-3 wide and per-step LLM spend is bounded; the ceiling still halts the run before the *next* wave. (Single-step units keep today's exact timing.)

**Merge — precise key-set + RAISE (Q2a).**
```python
written: dict[str, str] = {}          # artifact key -> child_id (cross-child collision check)
for flat, child_ctx, exec_struct in collected_in_unit_order:
    declared = {k.value for k in flat.step.writes}
    seeded   = {k.value for k in (set(flat.step.reads) | set(flat.step.reads_optional))}
    extra = set(child_ctx.data) - declared - seeded
    assert not extra, f"{flat.id} wrote undeclared artifacts {extra}"   # Q2a: undeclared write caught loudly
    for key in declared:
        if key not in child_ctx.data:
            continue                  # step legitimately skipped a write
        if key in written:
            raise RuntimeError(f"parallel write conflict on {key} "
                               f"between {written[key]} and {flat.id}")
        ctx.data[key] = child_ctx.data[key]
        written[key] = flat.id
```
A concurrent step **MUST write only its DECLARED writes.** We copy back **only the child's declared writes**, and assert the child wrote nothing outside `declared ∪ seeded_reads` — closing the hole where an undeclared `ctx.set_artifact` would be silently dropped (instead it is caught loudly). Same-key across two children **raises** (no last-writer-wins). This is unreachable in valid specs (the independence predicate gives disjoint write sets within a unit; A.2 rejects two writers of any artifact) — the RAISE and the assert are cheap defense-in-depth, **not** conflict-resolution machinery (a dict + `raise`, nothing more).

**Timeout branch.** A started thread can't be cancelled, so no mid-wave fail-fast: collect all, then report. `future.result(timeout=STEP_TIMEOUT_S)` raising `FutureTimeout` yields a synthetic `StepResult(ok=False, errors=["step_timeout"])` and, on the parent, a `record_step_trace(..., status="timeout", error={"type":"Timeout",...})`. `status` is a free `str` on the doc, so `"timeout"` is a new value distinct from `ok|skipped|error`. Its `stop_on_fail` treatment is identical to any non-ok child.

**Outcomes + break.** `outcomes.append` and the `stop_on_fail` break run on the parent, per child, in unit order, reusing the existing `_runbook_engine.py:187-216` logic verbatim. If any child in the unit is non-ok/non-skipped and `stop_on_fail`, break after finishing the unit's merge+emit.

**DoD — B.2.**
- **Merge correctness:** unit of two children with disjoint declared writes → after the unit `ctx.data` has both keys with the children's values; seeded read-snapshot keys are not duplicated.
- **Undeclared-write guard (Q2a):** a child that calls `set_artifact` for a key not in its `writes` → the merge `assert` fires (new test).
- **Conflict raises:** a validator-bypassing unit where two children write the same key → `run_steps` raises `RuntimeError` naming both ids.
- **Timeout:** a child sleeping past `STEP_TIMEOUT_S` → its doc `status == "timeout"`; the sibling completes and merges; `stop_on_fail` treats it as non-ok.
- **Cost single-threaded:** recorded `CostMeter` spend for a unit equals the sum of per-child floats; a unit whose summed cost crosses the ceiling raises `CostCeilingExceeded` on the parent (with documented post-barrier timing).
- **`_seq` single-threaded (both counters):** a patched `EventDispatcher.emit` and `StepTraceSink.on_step` record `threading.get_ident()`; assert every call's thread id equals the main thread id for a concurrent unit (covers **both** `EventDispatcher._seq` and `StepTraceSink._seq`).
- **Trace determinism:** `seq` values for a concurrent unit are contiguous and ordered by `branch_index`; two runs → identical `(step_id, seq, branch_index)` triples.
- **Captured-output correctness:** a child whose declared write is later overwritten by merge order still traces its **own** written value (because capture happened on the worker pre-merge).

### B.3 — Integration through `runner.py`

| File | CHANGED | Change |
|---|---|---|
| `backend/app/interval/runner.py` | unchanged | The `run_steps(graph, run_ctx, deps, wrappers=engine_invariants(meter=meter))` call (`:407-412`) is untouched; parallelism is internal to `run_steps`, gated by the flag. `stop_on_fail` defaults `True`. |

**DoD — B.3.**
- `_run_account_pipeline` flag **off** → identical result dict vs current build on a reference account (golden).
- Flag **on** on a spec with a real independent pair → same final published artifact and same outcomes; the pair's docs carry `parallel_group`/`branch_index`; wall-time strictly less than sequential for a fixture with two artificially slow independent steps (sanity that concurrency engaged).
- `release_post_pipeline_guards(ctx, aid)` (`try/finally` around `:367-414`) still runs exactly once; no guard acquired/released inside a wave.

---

## 4. Phase C — Tracing read surface (DATA-ONLY)

`parallel_group` + `branch_index` are persisted by A.3 + B.2. This phase surfaces them on the **read route only**. **The `flowGraph.ts` / `PipelineFlowDiagram.tsx` UI work is explicitly DEFERRED and out of scope:** that diagram is a hand-authored, hardcoded structural mirror of the spec with a manual "parallel" note — surfacing the runtime fields does not, and cannot, make it auto-reflect runtime concurrency. Phase C ships the data; the diagram UI remains future work.

| File | CHANGED | Change |
|---|---|---|
| step-output read route (the endpoint serializing `StepOutputDocument` to the run-detail view) | Ensure `parallel_group` and `branch_index` appear in the serialized response (likely zero code change if it serializes the full document — **confirm at implementation time**, do not assume). |

**DoD — Phase C.**
- The read route for a run with a concurrent unit returns each step's `parallel_group` (sibling id-list) and `branch_index`; sequential steps return both `null`.
- A run with zero concurrent units (flag off, or linear spec) serializes identically to today (both fields `null`).
- No frontend change; the `flowGraph.ts` step-id lock test still passes (ids unchanged).

---

## 5. Independence predicate + wave scheduler (pseudocode)

```python
# scheduler.py — pure; no ctx, deps, ContextVars, or I/O.
EXCLUDED_WRITES = {ArtifactKey.SAFETY_VERDICT, ArtifactKey.REPLY_VERDICT,
                   ArtifactKey.PUBLISHED_POST, ArtifactKey.REPLY_RESULT}

def _independent(a, b, W, R):                 # pairwise: WAW + WAR + RAW
    return (not (W[a] & W[b])                 # no shared write key  (WAW on shared ctx.data)
            and not (W[a] & R[b])             # b doesn't read what a writes  (RAW/WAR)
            and not (W[b] & R[a]))            # symmetric

def plan_execution_units(flat):
    n = len(flat)
    W = [set(f.step.writes) for f in flat]
    R = [set(f.step.reads) | set(f.step.reads_optional) for f in flat]   # optional → predicate only
    excluded = {i for i in range(n) if W[i] & EXCLUDED_WRITES}

    producers = defaultdict(list)             # full writer list per key, declared order
    for i in range(n):
        for w in W[i]:
            producers[w].append(i)
    # deps uses reads ONLY (not reads_optional) — see A.1 decision
    reads_only = [set(f.step.reads) for f in flat]
    deps = [ {p for r in reads_only[i] for p in producers[r] if p < i} for i in range(n) ]

    indeg = [len(deps[i]) for i in range(n)]
    succ = defaultdict(set)
    for i in range(n):
        for p in deps[i]:
            succ[p].add(i)

    done, remaining, units = [False]*n, n, []
    while remaining:
        wave = sorted(i for i in range(n) if not done[i] and indeg[i] == 0)
        assert wave, "ready-set empty but work remains => cycle (impossible post-validator)"
        groups = []
        for i in wave:                        # declared order ⇒ deterministic grouping
            if i in excluded:
                groups.append([i]); continue
            for g in groups:
                if g[0] in excluded:
                    continue
                if all(_independent(i, m, W, R) for m in g):
                    g.append(i); break
            else:
                groups.append([i])            # own singleton (sequential)
        for g in sorted(groups, key=lambda gg: gg[0]):
            units.append([flat[i].id for i in sorted(g)])   # ids by declared index ⇒ stable branch_index
            for i in g:
                done[i] = True; remaining -= 1
                for j in succ[i]:
                    indeg[j] -= 1
    return units
```

Output is an ordered `list[list[str]]` of full dotted ids: outer order = execution order; length-1 = sequential (guardian/terminal always here); length>1 = concurrent. Review-before-consumer ordering is **free**: the consumer declares `reads={SAFETY_VERDICT,…}`, the reviewer is its producer, so `reviewer ∈ deps[consumer]` and the consumer can't enter a wave until the reviewer is `done` — no special case (verified against `publish_post` reading `SAFETY_VERDICT`, post_tick.py:95). Complexity: `O(n·K + E)` build + Kahn, worst-case `O(n²·K)` grouping; negligible at n≈10-20, waves 2-3 wide.

---

## 6. Parallel executor (pseudocode) — worker = PURE, parent = SIDE EFFECTS

```python
# _runbook_engine.py
STEP_TIMEOUT_S = 120.0
MAX_WORKERS = 4

def run_steps(steps, ctx, deps, *, stop_on_fail=True, wrappers=()):
    log, outcomes = [], PipelineOutcomeRepository()
    flat_steps = flatten_steps(steps)

    if not settings.pipeline_parallel_enabled:
        # ... EXISTING sequential loop (_runbook_engine.py:182-218), byte-identical ...
        # (each step: exec = _execute_step(flat, ctx, deps, wrappers=wrappers);
        #             _emit_and_trace_step(flat, exec)  — same call order as today)
        return RunbookResult(ctx, log)

    by_id = {f.id: f for f in flat_steps}
    for unit in plan_execution_units(flat_steps):
        if len(unit) == 1:
            flat = by_id[unit[0]]
            exec_ = _execute_step(flat, ctx, deps, wrappers=wrappers)   # PARENT thread (pure)
            _emit_and_trace_step(flat, exec_)                            # PARENT thread (side effects)
            results = [(flat, exec_.result, exec_.entry)]
        else:
            results = _run_wave(unit, by_id, ctx, deps, wrappers)        # below

        for flat, result, entry in results:                             # parent, unit order
            log.append(entry)
            # ... EXISTING outcomes.append + stop_on_fail logic (:187-216) per child ...
        if stop_on_fail and any(not r.ok and not r.skipped for _, r, _ in results):
            break
    return RunbookResult(ctx, log)


def _run_wave(unit, by_id, ctx, deps, wrappers):
    children = [dataclasses.replace(by_id[sid], parallel_group=list(unit), branch_index=pos)
                for pos, sid in enumerate(unit)]          # ids already sorted by declared index
    # guardian_wrapper only fires on EXCLUDED 'compose_until_safe' (never in a wave);
    # cost_wrapper is deferred to the parent → children run with NO wrappers.
    futs = {}
    with ThreadPoolExecutor(max_workers=min(len(children), MAX_WORKERS)) as ex:
        for flat in children:
            child_ctx = _make_child_ctx(ctx, flat)        # deepcopy-seeded read snapshot
            cv = contextvars.copy_context()               # isolates _run_llm_cost_usd per worker
            # WORKER EXECUTES ONLY — no emit, no trace, no _seq mutation, no cost accounting:
            futs[flat.id] = (flat, child_ctx,
                             ex.submit(cv.run, _execute_step_for_worker, flat, child_ctx, deps))
        collected = []
        for flat in children:                             # collect-all (no fail-fast)
            _, child_ctx, fut = futs[flat.id]
            try:
                exec_, child_cost = fut.result(timeout=STEP_TIMEOUT_S)
            except FutureTimeout:
                exec_, child_cost = _synthetic_timeout_exec(flat), 0.0
            collected.append((flat, child_ctx, exec_, child_cost))

    # ---------- barrier: everything below is single-threaded on the PARENT ----------
    written = {}
    for flat, child_ctx, exec_, _ in collected:           # unit order
        declared = {k.value for k in flat.step.writes}
        seeded   = {k.value for k in (set(flat.step.reads) | set(flat.step.reads_optional))}
        assert not (set(child_ctx.data) - declared - seeded), f"{flat.id} wrote undeclared keys"
        for key in declared:
            if key not in child_ctx.data:
                continue
            if key in written:
                raise RuntimeError(f"parallel write conflict on {key} "
                                   f"between {written[key]} and {flat.id}")
            ctx.data[key] = child_ctx.data[key]; written[key] = flat.id

    results = []
    for flat, _, exec_, child_cost in collected:          # unit order
        meter.check_before(flat.id)                       # ceiling fires here (parent, post-barrier)
        meter.record_after(flat.id, child_cost)
        _emit_and_trace_step(flat, exec_)                 # bumps EventDispatcher._seq + StepTraceSink._seq, PARENT ONLY
        results.append((flat, exec_.result, exec_.entry))
    return results
```

`_execute_step_for_worker` wraps `_execute_step` to also `return exec_, drain_run_llm_cost_usd()` (the drain reads the worker's isolated `_run_llm_cost_usd` ContextVar). **`_execute_step` captures inputs/outputs against `child_ctx` on the worker, before the merge** — so a value later overwritten by parent merge order still traces the child's own value (the `record_step_trace` `capture_artifacts_full` reads from the child's scratch ctx carried in `exec_`, not the merged parent ctx). `_make_child_ctx` is as in B.1 (deepcopy seed). `_synthetic_timeout_exec` builds a struct with `result=StepResult(ok=False, errors=["step_timeout"])`, `status="timeout"`, and an `error` dict, so `_emit_and_trace_step` writes a proper timeout doc on the parent.

---

## 7. Test matrix

| # | Invariant | Where enforced | Test |
|---|---|---|---|
| 1 | Leaf dotted ids unchanged | engine hint over flat list; no `CompositeSpec` | golden `step_id` set equal flag-on vs flag-off |
| 2 | **WAW racing pair REJECTED from grouping** | `_independent` (A.1) | A.1 WAW guard: two same-key writers → **two singletons**, never co-scheduled |
| 3 | WAR pair serialized | `_independent` (A.1) | A.1 WAR guard |
| 4 | Multi-writer reader waits for all | `producers` full list + `deps` (A.1) | A.1 multi-writer RAW: `deps[2]=={0,1}` |
| 5 | `reads_optional` keeps pair apart but doesn't force cross-wave order | predicate uses `reads∪reads_optional`; `deps` uses `reads` (A.1) | A.1 reads_optional test |
| 6 | Review-before-consumer ordering | dep edge via reviewer's write key (A.1) | A.1 verdict-dependency test |
| 7 | Determinism | declared-index tiebreaks (A.1) | `plan(x)==plan(x)` ×100 |
| 8 | No same-key concurrent write | A.2 validator + B.2 RAISE | A.2 `multiple_writers` + B.2 conflict-raises |
| 9 | No undeclared writes lost | B.2 merge assert | B.2 undeclared-write guard test (Q2a) |
| 10 | Guardian/terminal never grouped | EXCLUDED set (A.1) | A.1 EXCLUDED test |
| 11 | **Trace never vanishes on failure/timeout** | `_emit_and_trace_step` on parent (B.2) | child raises → doc `status="error"` + populated `error`; child times out → doc `status="timeout"`; sibling still traced |
| 12 | All `_seq` single-threaded (both dispatcher + sink) | parent-only emit/trace (B.2) | B.2 thread-id assertion on `EventDispatcher.emit` **and** `StepTraceSink.on_step` |
| 13 | Cost single-threaded + summed | parent `check_before`/`record_after` (B.2) | B.2 cost-sum + ceiling-raise test |
| 14 | Captured output is the child's own write | `_execute_step` captures on worker pre-merge (B.0/B.2) | B.2 captured-output-correctness test |
| 15 | **Flag off == byte-identical** | B.0 guard + B.0 split composition | golden parity B.0/B.3 (steps log + event sequence) |
| 16 | Acyclic assumption documented | `assert wave` (A.1) | A.1 cyclic-input trips assert |

All new test files live under `backend/tests/unit/pipeline/` (scheduler, validator-single-writer, engine concurrency) and `backend/tests/unit/` (model field round-trip) — matching the real layout.

---

## 8. Rollout

1. **Land Phase A** on `feat/platform-overhaul`. Pure scheduler + validator rule + additive fields; flag does not yet exist or is unread by the loop. Full suite green; golden trace unchanged. Ships with zero behavioral change. (**Verified-sound — safe to land first.**)
2. **Land Phase B with `pipeline_parallel_enabled=False`** (default). The B.0 split refactor makes the *sequential* path go `_execute_step → _emit_and_trace_step`; verify byte-identical golden parity (test 15) before merging. With the flag off the scheduler is computed-but-unconsumed and the wave executor is dead code — structurally safe to ship.
3. **Canary one account.** Flip `pipeline_parallel_enabled=True` for a single account (or a per-account override if available; otherwise a short-lived global toggle on a low-traffic slot). Watch: identical final published artifact vs the sequential baseline, `parallel_group`/`branch_index` populated on the analyze pair, no `parallel write conflict`/undeclared-write asserts, `seq` contiguous-and-ordered, cost-meter totals match. The genuine win on the real spec is the `analyze_external` / `analyze_own` LLM-brief pair (the write-only roots are a marginal extra) — confirm the wall-time delta there.
4. **Enable globally** once the canary holds across several runs. Phase C (read-route fields) can land any time after B since it is additive `null`-default data; the diagram UI remains future work.

**Files (absolute).**
NEW: `…/backend/app/pipeline/scheduler.py`; `…/backend/tests/unit/pipeline/test_scheduler.py`; `…/backend/tests/unit/pipeline/test_validator_single_writer.py`.
CHANGED: `…/backend/app/pipeline/_runbook_engine.py` (split `_run_step_with_progress` → `_execute_step`+`_emit_and_trace_step`; `run_steps` flag branch + `_run_wave`/`_make_child_ctx`); `…/backend/app/pipeline/types/flow.py` (`FlatStep` +2 fields); `…/backend/app/pipeline/spec/validator.py` (`_check_single_writer`, wire R4/R5); `…/backend/app/models/step_output.py` (+2 fields after `parent_id`); `…/backend/app/pipeline/events/step_trace.py` (passthrough after `:81`); `…/backend/app/core/config.py` (`pipeline_parallel_enabled: bool = False`, alongside `pipeline_cost_ceiling_usd` at `:100`); `…/backend/app/interval/runner.py` (no edit; `:407-412` confirmed unchanged); step-output read route (Phase C; confirm whether full-doc serialization already includes the fields).

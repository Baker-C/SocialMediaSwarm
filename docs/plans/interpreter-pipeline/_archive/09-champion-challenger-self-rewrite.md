# Doc 09 — Champion/Challenger Evaluation + Self-Rewrite (the LEARN→BUILD loop closes)

> **Status:** Ready to implement. Authored cold from verified live code + the sibling plan docs; this slice has zero open questions.
> **Phase:** LEARN + BUILD — the back half of the Interpreter loop (MEASURE → LEARN → BUILD → RUN). MEASURE is doc `01`/`02`; RUN is doc `07`. This doc owns *deciding which spec wins* and *proposing the next spec*.
> **Scope:** Backend only. Three new services (`champion_challenger_service.py`, `spec_rewrite_service.py`, `spec_rollback.py`), one new LEARN job (`learn_job.py`) wired into the existing fixed APScheduler set, plus a thin soul-rewrite reuse of `voice_version_service` and a one-method add to doc `02`'s ledger repo (`list_for_soul_hash`, §3.1). No new RavenDB transactional machinery (there is none — §6), no new polling, no per-agent scheduler.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB + in-process APScheduler threadpool).
> **DB reality:** One account today — `JohnJames_News`. Promotion/rollback are sequential puts (RavenDB has no multi-doc transactions, the HTTP client has no CAS/If-Match — verified `app/infrastructure/ravendb_http.py:103-110`). We document the partial-write window and order writes fail-safe.

> **Cross-refs (shared types defined elsewhere — do NOT redefine here):**
> - `PipelineSpecDocument` (+ `StepSpec`, `CompositeSpec`, `default_pipeline_spec`), `PipelineSpecRepository` (`load`, `load_or_default`, `save`), `PipelineRevisionRepository` (`save`, `list_for_account`), `promote_challenger(...)`, and the `version_hash`/`version_seq`/`status`/`parent_hash` lifecycle are **doc `04`**. This doc *drives* promotion/rollback and *constructs challengers*; it does not redefine the model, the version service, or the base `promote_challenger` primitive — it calls them.
> - `validate_spec(doc, catalog) -> ValidationReport` and `compile_spec(doc, *, catalog=None) -> tuple[Step, ...]` are **doc `05`**. `ValidationReport` is a Pydantic model with `.ok: bool` and `.codes() -> list[str]` (doc `05` §5.2) — this doc branches on `report.ok` and logs `report.codes()`, never treats the return as a bare list. The self-rewrite is gated by the *same* `validate_spec` the runner uses; an unknown `tool_id` is rejected as `unknown_tool` (doc `05` R1).
> - The tool catalog is **doc `03`**, consumed through the `ToolCatalog` wrapper object (`catalog.get(tool_id)` / `tool_id in catalog` / `catalog.all()`), obtained from doc `03`'s `get_tool_catalog() -> ToolCatalog`. `validate_spec(doc, catalog)` requires that **object**, NOT the raw `build_tool_catalog() -> list[ToolCatalogDocument]`. This doc calls `get_tool_catalog()` once and passes the object straight to `validate_spec`; the proposer reads it (via `.all()` / per-tool `.proposable_params`) to know what an LLM may legally wire — it never invents a tool.
> - `OutcomeLedgerDocument` (`run_id`, `account_id`, `post_id`, `soul_hash`, `pipeline_hash`, `reward`, `recorded_at`) and `OutcomeLedgerRepository.list_for_pipeline_hash(pipeline_hash, *, account_id=None, limit=500)` are **doc `02`**. Reward attribution by `pipeline_hash`/`soul_hash` is read straight from the ledger.
> - **`pipeline_hash` is the WALKED spec's `version_hash`, NEVER an account accessor (CC-3).** Doc `04` §1's `pipeline_hash` pin states it: there is **no** `account.pipeline_version_hash` / `account.pipeline_hash` and no doc adds one (the spec lives in a separate `pipelinespecs/{account_id}` doc) — remove any such reference. Every comparison in §3 keys on `PipelineSpecDocument.version_hash` (`champ.version_hash`, `challenger.version_hash`, `champ.parent_hash`), read from the loaded spec doc — this doc never reads a pipeline hash off the account. The published-post stamp carries the **walked** spec's `version_hash` (doc `07` captures it from the loaded spec and threads it into `publish_post`): for a champion slot that is the champion hash, and for a challenger slot it is the **challenger's** hash — NOT `load_or_default(account_id).version_hash`, which is always the champion and would mis-attribute a challenger post (the §4.1 wrinkle). That walked hash is the value the ledger's `pipeline_hash` column carries and §3.1 scores each arm against.
> - `post_reward(row)` / `account_avg_reward(rows)` and `AccountMetricsDocument.avg_post_reward` are **doc `01`**. This doc consumes the reward scale; it never recomputes the reward formula.
> - `voice_version_service.bump_voice_version_if_needed(...)` + `compute_voice_hash(...)` are the **soul-pipeline** plan (`05-versioning.md`); soul self-rewrite reuses them verbatim (§5.3).

---

## 1. Why this doc exists (and what it is NOT)

After doc `07` the runner walks each account's **champion** `PipelineSpecDocument` as data, and after docs `01`/`02` every posted tweet earns a normalized `reward` keyed to the `pipeline_hash` and `soul_hash` that produced it. Two questions remain, and they are the whole reason the Interpreter exists:

1. **Which spec is actually better?** — Aggregate reward by `pipeline_hash` (and `soul_hash`) over a comparison window and decide whether a staged **challenger** out-performs the **champion** enough to promote, or whether a freshly-promoted champion has regressed enough to roll back. (`champion_challenger_service`.)
2. **What should the next spec be?** — Propose a NEW `PipelineSpecDocument` by **rewiring/reconfiguring existing catalog tools** (never writing tool code), gated by the same validator the runner uses, and stage it as a challenger. (`spec_rewrite_service`.) The soul gets the same treatment, reusing the soul version service.

**The settled defaults this doc implements (do not re-litigate):**
- **Manual promote, auto-rollback on hard regression.** A human (a button/endpoint, doc `07`/frontend) triggers promotion of a validated challenger. The *only* automatic mutating action is **rollback** when a promoted champion shows a hard regression against its parent. This is the conservative posture the architecture brief fixed.
- **Self-rewrite only WIRES + CONFIGURES catalog tools.** The proposer emits a spec that the doc `05` validator accepts; `unknown_tool` / non-`literal` config is rejected before anything is staged. No new tool code is ever written.
- **Routing rides the FIXED APScheduler jobs.** We do NOT add per-agent scheduling (explicitly DEFERRED — §4.3). Champion vs challenger execution is selected by **alternating slots** within the existing `scheduled_posting` cadence; LEARN runs on its own fixed cron job alongside `metrics_batch`.
- **No DB transactions.** Every promotion/rollback is a short sequence of plain puts; we order them so a crash leaves the *old* champion live, and we document the partial-write window honestly (§6).

**What this is NOT (explicit non-goals, do not build):**
- **NOT the reward function.** That is doc `01`. We read `reward` off ledger rows and average it; we never define the formula.
- **NOT the promotion primitive.** `promote_challenger(account_id, repo)` (the validate→activate→cleanup sequence of puts) is *defined* in doc `04` (`pipeline_spec_repository.py`). This doc decides *when* to call it and adds the *rollback* counterpart, but the low-level put ordering lives where doc `04` put it.
- **NOT per-agent / per-account scheduling.** Deferred, with the exact reason and the trivial future path in §4.3.
- **NOT a new metrics poll.** LEARN is pure arithmetic over ledger rows already in RavenDB — zero X-API calls (the `MEMORY.md → pipeline-search-and-metrics` cost incident is respected; see §7).

---

## 2. File-by-file plan

### NEW

| File | Role (one line) |
|---|---|
| `app/services/champion_challenger_service.py` | Aggregate reward by `pipeline_hash`/`soul_hash` from the ledger; the promote-eligibility + hard-regression decision rules; calls doc `04`'s `promote_challenger` and the new `rollback_to_parent`. |
| `app/services/spec_rewrite_service.py` | Propose a NEW `PipelineSpecDocument` (rewire/reconfigure catalog tools only), validate it with doc `05`'s `validate_spec`, and stage it as a `status="challenger"` spec. The builder-LLM call is one optional path; a deterministic "tweak one literal knob" path is the default. |
| `app/jobs/learn_job.py` | The fixed-cron LEARN entry point: for each active account, run auto-rollback checks, then (optionally) stage a challenger if none exists. Mirrors `metrics_job.py` shape exactly. |
| `app/services/spec_rollback.py` | `rollback_to_parent(account_id, repo)` — rebuild the parent champion from the revision archive and re-`save` it (a sequential put, no CAS). Kept tiny and separate so doc `04`'s `pipeline_spec_repository.py` stays the home of the *forward* promotion only. |
| `tests/unit/test_champion_challenger_service.py` | Reward aggregation by hash + every promote/rollback rule branch (windows, thresholds, insufficient-data → no-op). |
| `tests/unit/test_spec_rewrite_service.py` | A proposed challenger always passes `validate_spec`; an unknown-tool proposal is rejected and nothing is staged; the deterministic knob-tweak produces a *different* `version_hash`. |

### CHANGED

| File | Change (one line) |
|---|---|
| `app/main.py` | Import `run_learn_job` (beside `run_metrics_job`) and add one `sched.add_job(run_learn_job, CronTrigger(minute="20", timezone=tz), id="learn_batch", ...)` inside `_build_scheduler()` next to `metrics_batch` (§4.2). One job, fixed cron, mirrors the existing jobs. |
| `app/core/config.py` | Add the LEARN/promotion tunables (window sizes, thresholds, enable flags) to `Settings`, mirroring the `max_regeneration_rounds` / `pipeline_capture_payloads` style (§3.4). |
| `app/interval/runner.py` (`build_tick_context`) | Set `ctx.spec_status = _slot_spec_status(slot, mode)` from the `slot` **already computed at `runner.py:74`** — a single clock read, no recomputation drift. The helper `_slot_spec_status` lives in this file (§4.1). `interval_job.py` and `orchestrator.run_tick` need **no** change — `build_tick_context` is the one place the slot exists, so spec_status is derived there. |
| `app/interval/runner.py` (`_run_account_pipeline`) | Replace the doc `07` spec load (`PipelineSpecRepository().load_or_default(aid)`, `runner` §2.4 line 129) with a status-aware load: `_load_spec_for_status(aid, ctx.spec_status, repo)` (§4.1). The compile/validate/walk that follow are unchanged (doc `07`). |
| `app/interval/context.py` (`TickContext`) | Add `spec_status: str = "champion"` (§4.1) — a plain config field alongside `mode`/`bypass_post_cooldown`. Default `"champion"` keeps every non-scheduled call site (force-post, tests) on the champion. |
| `app/services/outcome_ledger_repository.py` (doc `02`) | Add **one** method `list_for_soul_hash(soul_hash, *, account_id=None, limit=500)` — a 6-line copy of doc `02`'s `list_for_pipeline_hash` (`:327-355`) with the where-clause column `pipeline_hash` → `soul_hash`. Feeds `score_soul_hash` (§3.1). No other change to doc `02`'s repo. |

### REUSED (verbatim, no change)

| File | Why it is reused as-is |
|---|---|
| `app/services/pipeline_spec_repository.py` (doc `04`) | `load(account_id, status)`, `load_or_default`, `save`, and `promote_challenger(...)` — the forward promotion primitive. This doc calls them; it does not edit them. |
| `app/services/pipeline_revision_repository.py` (doc `04`) | `list_for_account(account_id)` returns the immutable revision archive newest-or-oldest; rollback rebuilds the parent spec from a revision's `steps`. |
| `app/services/pipeline_version_service.py` (doc `04`) | `compute_pipeline_hash` / `bump_pipeline_version_if_needed` — a staged challenger auto-versions on `save`, identical to how a soul edit versions. |
| `app/services/voice_version_service.py` (soul plan) | `bump_voice_version_if_needed` + `compute_voice_hash` — soul self-rewrite (§5.3) reuses these so a proposed personality/posting_prompt edit versions + archives exactly like a manual edit. |
| `app/services/outcome_ledger_repository.py` (doc `02`) | `list_for_pipeline_hash(pipeline_hash, account_id=..., limit=...)` is the read path for "every scored outcome for a spec version". The service averages `reward` over these rows. |
| `app/pipeline/spec/validator.py` (doc `05`) | `validate_spec(doc, catalog)` — the SAME gate. A self-rewrite proposal that does not satisfy it is never staged. |
| `app/pipeline/spec/catalog.py` (doc `03`) | `get_tool_catalog() -> ToolCatalog` (the object passed to `validate_spec`); `ToolCatalog.all()` + each doc's `.proposable_params` — the proposer reads the closed tool set + the `literal` knobs it may set. (The raw `build_tool_catalog() -> list` is NOT the validator's `catalog` arg — use the wrapper object.) |
| `app/infrastructure/claude_client.py` | `get_claude_client()` → `ClaudeClient.messages_json_dict(system=..., user=..., max_tokens=...)` (verified lines 49-88) for the optional builder-LLM proposal path. Same client compose/guardian use. |
| `app/services/account_repository.py` | `list_active()` (verified lines 123-130) for the LEARN job's per-account loop; `load`/`save` for soul self-rewrite. |

---

## 3. `champion_challenger_service` — aggregate, decide, act

This service answers "is the challenger better?" and "did the new champion regress?" purely from ledger rows. It has **no scheduling logic** (that is the job, §4) and **no put ordering of its own for promotion** (that is doc `04`'s `promote_challenger`). It contributes the *decision rules* and the *rollback* put.

### 3.1 Aggregating reward by `pipeline_hash` and `soul_hash`

The ledger (`doc 02`) already lifts `pipeline_hash`, `soul_hash`, and the computed scalar `reward` to the top level of each `OutcomeLedgerDocument`, keyed `outcomeledger/{account_id}-{post_id}`. Aggregation is "load the rows for a hash, average the non-`None` rewards":

```python
# app/services/champion_challenger_service.py
from dataclasses import dataclass

from app.services.outcome_ledger_repository import OutcomeLedgerRepository


@dataclass(frozen=True)
class SpecScore:
    pipeline_hash: str
    n_scored: int          # rows with a non-None reward (the comparison sample size)
    n_total: int           # rows that exist (scored + still-None/unpolled)
    avg_reward: float | None   # mean of the non-None rewards, or None if n_scored == 0


def score_pipeline_hash(
    pipeline_hash: str,
    *,
    account_id: str,
    limit: int = 500,
    ledger: OutcomeLedgerRepository | None = None,
) -> SpecScore:
    """Mean reward over the ledger rows attributed to one pipeline version.
    None rewards (post not yet polled — doc 01/02 distinguish None from a real 0)
    are EXCLUDED from the average and counted separately, never treated as 0."""
    ledger = ledger or OutcomeLedgerRepository()
    rows = ledger.list_for_pipeline_hash(pipeline_hash, account_id=account_id, limit=limit)
    scored = [r.reward for r in rows if isinstance(r.reward, (int, float))]
    return SpecScore(
        pipeline_hash=pipeline_hash,
        n_scored=len(scored),
        n_total=len(rows),
        avg_reward=(sum(scored) / len(scored)) if scored else None,
    )
```

> **Decision Defense — why aggregate off the ledger, not off `TrackedPostDocument`/`AccountMetricsDocument`?** Doc `02` already built the ledger precisely as the *attribution-shaped* view: `pipeline_hash`/`soul_hash` are top-level (cheaply `where`-able) and `reward` is a stored scalar. `AccountMetricsDocument.avg_post_reward` (doc `01`) is the account-wide average across *all* pipeline versions — useful for the dashboard, useless for A/B because it mixes champion and challenger posts. `TrackedPostDocument` buries the hashes inside `creation_metrics` (un-`where`-able) and has no `reward` scalar. The ledger is the one surface that lets us say "average reward for *this* hash" in one query. We reuse it; we do not recompute reward (doc `01` owns the formula).

> **`soul_hash` aggregation rides the same path — but needs its own read.** The ledger carries `soul_hash` top-level too. `list_for_pipeline_hash` (doc `02`) is hard-keyed on the `pipeline_hash` column, so it **cannot** return rows for a `soul_hash`; `score_soul_hash` needs a soul-keyed read. Doc `02`'s repo does not ship one, so this slice adds **one** tiny sibling method, `OutcomeLedgerRepository.list_for_soul_hash(soul_hash, *, account_id=None, limit=500)`, that is a byte-for-byte copy of `list_for_pipeline_hash` (doc `02` §4.2, `:327-355`) with the single where-clause column changed from `pipeline_hash` to `soul_hash`. (Owned here, not in doc `02`, because soul-scoring is this doc's consumer; it is a 6-line mirror, not new infrastructure.) `score_soul_hash(soul_hash, *, account_id, limit=500, ledger=None)` is then identical to `score_pipeline_hash` but calls `ledger.list_for_soul_hash(...)` and returns a `SpecScore`-shaped result keyed on the soul hash. We keep two tiny score functions rather than one field-parameterized function so each call site reads literally ("score this pipeline version" / "score this soul version") — the simpler, more honest option per CLAUDE.md. `score_soul_hash` serves the dashboard's soul A/B view only; the autonomous LEARN job (§4.2) never calls it (soul rewrite is manual, §5.3).

### 3.2 The promote-eligibility rule (advisory; promotion stays manual)

Promotion is **manual** by default, so this rule does **not** call `promote_challenger`. It produces a structured *recommendation* the dashboard/endpoint surfaces, so a human promotes with eyes open. (A future "auto-promote" flag, §3.4, would let the LEARN job act on it — defaulted off.)

```python
@dataclass(frozen=True)
class PromotionVerdict:
    eligible: bool
    reason: str                 # machine code: "insufficient_window" | "no_improvement" | "improved"
    champion: SpecScore
    challenger: SpecScore
    delta: float | None         # challenger.avg_reward - champion.avg_reward, or None


def evaluate_promotion(
    account_id: str,
    *,
    champion_hash: str,
    challenger_hash: str,
    min_window: int,            # settings.learn_promote_min_window
    min_improvement: float,     # settings.learn_promote_min_improvement
    ledger: OutcomeLedgerRepository | None = None,
) -> PromotionVerdict:
    champ = score_pipeline_hash(champion_hash, account_id=account_id, ledger=ledger)
    chal = score_pipeline_hash(challenger_hash, account_id=account_id, ledger=ledger)

    # Both arms need a minimum scored sample, else we have no signal (NOT a verdict).
    if champ.n_scored < min_window or chal.n_scored < min_window:
        return PromotionVerdict(False, "insufficient_window", champ, chal, None)

    delta = (chal.avg_reward or 0.0) - (champ.avg_reward or 0.0)
    if delta >= min_improvement:
        return PromotionVerdict(True, "improved", champ, chal, delta)
    return PromotionVerdict(False, "no_improvement", champ, chal, delta)
```

**Windows + thresholds (resolved, tunable in config §3.4):**
- `min_window = learn_promote_min_window` (**default 10**): each arm must have at least 10 *scored* (polled, non-`None`) posts before any comparison. Below this the verdict is `insufficient_window` and nothing happens. This is the comparison *sample-size* window, not a time window — a count of measured posts is a more honest "do we have signal" gate than wall-clock, given posting cadence varies.
- `min_improvement = learn_promote_min_improvement` (**default 0.02**): the challenger must beat the champion's average reward by at least 0.02 (on the doc `01` `[0,1]` scale) to be *eligible*. A smaller delta is noise at N≈10; 0.02 is ~one rung on the engagement saturation curve. Tunable.

> **Decision Defense — why a sample-size window, not a time window?** Doc `01` is explicit that reward is `None` until a post is polled, and that `None` must never count as `0`. A 7-day time window would compare a champion's mature, fully-polled posts against a challenger's freshest, mostly-`None` posts — biasing *against* the challenger exactly when it is newest. Counting *scored* posts equalizes maturity: both arms are judged only on posts that have a real reward. This mirrors doc `01`'s `None`-excludes-from-average contract precisely.

### 3.3 The hard-regression rule (the ONE automatic action: rollback)

A promotion can be a mistake the metrics only reveal afterward. The single automatic mutating action is **rollback to the parent champion** when the *current* champion has regressed hard against the version it replaced. The parent is identified by `champion_spec.parent_hash` (doc `04` sets it on promotion).

```python
@dataclass(frozen=True)
class RegressionVerdict:
    regressed: bool
    reason: str                 # "no_parent" | "insufficient_window" | "stable" | "hard_regression"
    current: SpecScore
    parent: SpecScore | None
    drop: float | None          # parent.avg_reward - current.avg_reward, or None


def evaluate_regression(
    account_id: str,
    *,
    current_hash: str,
    parent_hash: str | None,
    min_window: int,            # settings.learn_rollback_min_window
    hard_drop: float,           # settings.learn_rollback_hard_drop
    ledger: OutcomeLedgerRepository | None = None,
) -> RegressionVerdict:
    if not parent_hash:
        return RegressionVerdict(False, "no_parent", score_pipeline_hash(current_hash, account_id=account_id, ledger=ledger), None, None)
    cur = score_pipeline_hash(current_hash, account_id=account_id, ledger=ledger)
    par = score_pipeline_hash(parent_hash, account_id=account_id, ledger=ledger)
    if cur.n_scored < min_window or par.n_scored < min_window:
        return RegressionVerdict(False, "insufficient_window", cur, par, None)
    drop = (par.avg_reward or 0.0) - (cur.avg_reward or 0.0)
    if drop >= hard_drop:
        return RegressionVerdict(True, "hard_regression", cur, par, drop)
    return RegressionVerdict(False, "stable", cur, par, drop)
```

**Rollback window + threshold (resolved):**
- `learn_rollback_min_window` (**default 10**): same sample-size gate — we do not roll back on a handful of posts.
- `learn_rollback_hard_drop` (**default 0.05**): a *hard* regression is the parent out-scoring the current champion by ≥ 0.05 average reward — deliberately **larger** than the promote threshold (0.02). Promotion is hopeful and reversible; rollback is destructive of an operator's choice, so it demands a bigger, unambiguous signal. The asymmetry is intentional and tunable.

When `regressed is True`, the LEARN job calls `rollback_to_parent` (§3.5). This is the only place the service mutates state without a human.

### 3.4 Config additions (`app/core/config.py`)

Mirrors the existing `Settings` field style (verified `config.py:53,98`). All defaults are conservative; `0`/`False` disables the corresponding behavior.

```python
# ── Interpreter LEARN / champion-challenger ──
learn_enabled: bool = True                  # master switch for the learn_batch job
learn_auto_rollback_enabled: bool = True    # the ONE automatic action; off => recommend only
learn_auto_promote_enabled: bool = False    # DEFAULT manual promote; on => job promotes on "improved"
learn_propose_challenger_enabled: bool = True   # stage a challenger when none exists
learn_promote_min_window: int = 10          # min SCORED posts per arm before A/B comparison
learn_promote_min_improvement: float = 0.02 # challenger must beat champion by this avg reward
learn_rollback_min_window: int = 10         # min SCORED posts per arm before rollback
learn_rollback_hard_drop: float = 0.05      # parent must beat current champion by this to roll back
learn_use_builder_llm: bool = False         # off => deterministic knob-tweak proposer (§5.2)
challenger_slot_every: int = 4              # run the challenger on 1-in-N posting slots (§4.1)
```

> **Decision Defense — `learn_auto_promote_enabled` exists but defaults `False`.** The brief fixes "manual promote, auto-rollback". The flag is the *seam* for a future "let it promote on a strong, sustained win" without re-plumbing — it costs one `if` in the job. Defaulting it off honors the settled default; shipping the seam avoids a second editing pass later. Auto-*rollback* defaults on because it is the safety net the brief explicitly wants automatic.

### 3.5 `rollback_to_parent` — a sequential put, no CAS (`app/services/spec_rollback.py`)

Rollback rebuilds the parent champion's `steps` from the revision archive and re-`save`s it as the live champion. There is no challenger involved and no second doc to coordinate, so it is a single mutating put through `PipelineSpecRepository.save` (which re-versions + archives via doc `04`).

```python
"""Roll a regressed champion back to the version it replaced. Sequential put,
no CAS (RavenDB has none — verified ravendb_http.py:103-110). One mutating write
to the champion doc; a crash before it leaves the regressed champion live (safe:
the next LEARN tick re-detects and retries)."""

from __future__ import annotations

from app.models.pipeline_spec import PipelineSpecDocument
from app.services.pipeline_revision_repository import PipelineRevisionRepository
from app.services.pipeline_spec_repository import PipelineSpecRepository


def rollback_to_parent(
    account_id: str,
    *,
    parent_hash: str,
    repo: PipelineSpecRepository | None = None,
    revisions: PipelineRevisionRepository | None = None,
) -> PipelineSpecDocument | None:
    """Re-promote the parent (identified by version_hash) as champion. Returns the
    new champion spec, or None if the parent revision cannot be found (no fabrication)."""
    repo = repo or PipelineSpecRepository()
    revisions = revisions or PipelineRevisionRepository()

    rev = next(
        (r for r in revisions.list_for_account(account_id) if r.version_hash == parent_hash),
        None,
    )
    if rev is None:
        return None  # parent not archived → cannot honestly reconstruct; skip (logged by caller)

    current = repo.load(account_id, "champion")
    # Seed the restored doc with the OUTGOING champion's version stamp so repo.save's
    # bump_pipeline_version_if_needed takes the "hash changed" branch and INCREMENTS the
    # seq (current.version_seq → +1), minting a NEW revision for the rollback. If we left
    # version_hash=None and version_seq=1 (the model defaults), the bump's `if not prev:`
    # branch would re-stamp seq=1 and OVERWRITE the original v1 revision (data loss) — see
    # doc 04 §5a bump logic. Carrying the current stamp forward is what makes the timeline
    # honestly read "v5 (rollback of v4 to v3's steps)" rather than resetting to v1.
    restored = PipelineSpecDocument(
        account_id=account_id,
        steps=list(rev.steps),                 # the parent's exact step tree (immutable archive)
        status="champion",
        parent_hash=(current.version_hash if current else None),  # lineage: forked from the regressed one
        version_seq=(current.version_seq if current else 1),      # continue the lineage, not reset to 1
        version_hash=(current.version_hash if current else None), # non-empty prev → bump takes the increment branch
    )
    repo.save(restored)  # PUT: champion = restored parent steps; bump mints v{current.seq+1}
    return restored
```

> **Decision Defense — why rebuild from the revision archive instead of flipping a status flag?** A champion can only ever be a `pipelinespecs/{account_id}` doc (doc `04`), and the regression we are undoing already overwrote it. The *parent's* steps survive only in `pipelinerevisions/{account_id}-v{seq}` (doc `04`'s immutable archive). Rebuilding from there is the single source of truth for "what the parent actually was"; it is also exactly the mechanism doc `04` §6 already named for rollback ("rebuild a `PipelineSpecDocument` from its `steps` → `repo.save`"). We do not invent a parallel path. **Carrying the outgoing champion's `version_seq`/`version_hash` onto the restored doc is load-bearing:** `repo.save` → `bump_pipeline_version_if_needed(restored, previous_hash=restored.version_hash)` then sees a non-empty `prev` that differs from the restored steps' hash, so it takes the increment branch and mints `v{current.seq+1}` with a fresh revision — the timeline honestly shows "v5 (rollback of v4 to v3's steps)". Leaving `version_hash=None` (seq default 1) would instead drive the bump's `if not prev:` branch, re-stamping seq=1 and clobbering the original v1 revision (verified against doc `04` §5a). The restored steps' content hash will differ from the outgoing champion's (we changed the steps back to the parent's), so the bump never short-circuits as a no-op.

---

## 4. Routing on FIXED APScheduler jobs (alternate slots)

The scheduler set is fixed and small (verified `main.py:41-97`): `scheduled_posting` (the posting tick), `engagement_poll` (:05), `early_engagement_poll` (every 15m), `metrics_batch` (:10), `oauth2_refresh`. We add **one** job and we do **not** add per-account scheduling.

### 4.1 Champion vs challenger by alternating slots

The posting tick fires on clock-aligned minute marks (`_posting_trigger`, `main.py:28-38`); each fire is one **slot**. The slot label is produced by `current_interval_slot_key()` (verified `app/services/account_repository.py:180-187`, format `"%Y-%m-%d-%H-%M"`, e.g. `"2026-06-17-14-00"`) and is **already computed once** in `build_tick_context` at `runner.py:74` and stored as `ctx.slot` (`runner.py:87`). We run the **challenger on 1-in-N slots** (`settings.challenger_slot_every`, default 4) and the **champion on the rest**, deriving `spec_status` from *that one already-computed slot string* — so there is exactly **one** clock read per tick and zero recomputation drift. `_slot_spec_status` takes the slot as an argument (it does **not** call `current_interval_slot_key()` again) and lives in `runner.py` next to `build_tick_context`:

```python
# app/interval/runner.py — pure helper beside build_tick_context (NOT in interval_job)
def _slot_spec_status(slot: str, mode: TickMode) -> str:
    """Run the challenger on 1-in-N slots so a staged variant accrues its own
    attribution rows; the rest run the champion. Pure function of the slot string
    + a fixed cron job — NOT a per-agent scheduler (§4.3). Forced (manual) ticks
    always run the champion: a human force-post must not silently land on a variant."""
    if mode != "scheduled":
        return "champion"
    every = max(2, int(settings.challenger_slot_every))
    bucket = int(slot.replace("-", ""))            # deterministic integer index from the slot
    return "challenger" if (bucket % every == 0) else "champion"
```

`build_tick_context` sets it from the slot it just computed, so **no new parameter threads through `interval_job` or `orchestrator.run_tick`** — the slot only exists inside `build_tick_context`, so that is the one honest place to derive the status:

```python
# app/interval/runner.py — inside build_tick_context, right after `slot = current_interval_slot_key()` (runner.py:74)
    slot = current_interval_slot_key()
    spec_status = _slot_spec_status(slot, mode)        # NEW — single clock read, no drift
    ...
    ctx = TickContext(
        ...
        slot=slot,
        mode=mode,
        spec_status=spec_status,                       # NEW — carried on the context (§2 CHANGED)
        ...
    )
```

The runner's spec load (doc `07` §2.4, `runner.py:129`, today `spec = PipelineSpecRepository().load_or_default(aid)`) becomes a status-aware load through doc `04`'s repo — there is **no** `load_active_spec` and **no** `SEED_SPEC` symbol (**CC-5** removes both; doc `04`'s §6b-bis confirms there is no `load_active_spec`, and any stale prose is superseded — the canonical entry point is `PipelineSpecRepository().load_or_default(account_id, kind="post")`). A tiny helper keeps the call site one line:

```python
# app/interval/runner.py — replaces the doc-07 `load_or_default(aid)` line at runner.py:129
def _load_spec_for_status(account_id: str, status: str, repo: PipelineSpecRepository):
    """Champion slot → the live champion (or seeded baseline). Challenger slot →
    the staged challenger if one exists, else fall back to champion-or-baseline.
    Uses ONLY doc 04's repo API (load / load_or_default); no new repo method."""
    if status == "challenger":
        challenger = repo.load(account_id, "challenger")   # doc 04 §6b — None when unstaged
        if challenger is not None:
            return challenger
    return repo.load_or_default(account_id)                 # doc 04 §6b — champion or baseline

# at runner.py:129:
spec = _load_spec_for_status(aid, ctx.spec_status, PipelineSpecRepository())
```

`PipelineSpecRepository.load(account_id, "challenger")` (doc `04` §6b) returns `None` when no challenger doc exists, so a "challenger slot" with nothing staged falls straight back to `load_or_default(aid)` (the champion, or the seeded baseline if even that is absent) — **no challenger ⇒ byte-identical to today's behavior.** The challenger's posts carry *its own* `version_hash` as `pipeline_hash` because doc `02` stamps `creation_metrics.pipeline_hash = PipelineSpecRepository().load_or_default(account_id).version_hash`… — **with one wrinkle the implementer must honor:** doc `02`'s default stamp reads `load_or_default` (always champion), which would mis-attribute a challenger-slot post to the champion hash. So when `ctx.spec_status == "challenger"` and a challenger actually ran, the stamp must use the **walked** spec's `version_hash`, not `load_or_default`. Doc `07` already resolves this generically: it captures `spec.version_hash` from the *loaded* spec and hands that to `publish_post` (doc `07` §7; the no-account-accessor pin is doc `04` §1, **CC-3**). Because `_load_spec_for_status` returns the exact spec that is compiled and walked, `spec.version_hash` is the correct `pipeline_hash` for either arm with no extra work — the implementer must thread the **walked `spec.version_hash`** (not a fresh `load_or_default` call) into the attribution stamp, which is precisely doc `07`'s contract. §3.1 then scores each arm by its own hash.

> **Decision Defense — alternating slots vs. a separate challenger schedule.** The brief says "alternate slots; per-agent scheduling is DEFERRED." A separate APScheduler job for the challenger would (a) double the posting cadence (cost + X-rate risk — the very thing `MEMORY.md` warns against), and (b) require its own slot/lock coordination against the champion job. Selecting `spec_status` *within the existing single posting tick* keeps exactly one posting job, one slot-claim path, one lock per (account, slot) — the challenger reuses the entire idempotency machinery doc `07` already relies on. It is the strictly smaller, safer change. The 1-in-N ratio (not 1-in-2) keeps the champion dominant in production while the challenger still accrues a steady trickle of attribution rows.

> **Decision Defense — derive `spec_status` inside `build_tick_context`, not in `interval_job`.** An earlier shape computed the status in `interval_job` and threaded a `spec_status` kwarg through `run_tick → build_tick_context → TickContext`. That is two edits more (orchestrator + interval_job) **and** it reads the wall clock a *second* time (`current_interval_slot_key()` inside the helper, independent of the slot `build_tick_context` already computed at `runner.py:74`). On a tick firing within ~1s of an interval boundary those two reads can land in different slots, so the status decision and the slot a post is attributed to could disagree on a knife-edge. Deriving the status from the **single** `slot` already computed in `build_tick_context` removes that failure mode entirely (one clock read, one slot, one decision), removes two file edits, and makes the force-post gating trivial (`build_tick_context` already knows `mode`). This is the strictly more elegant option (CLAUDE.md §2): fewer surgical changes, no possible drift.

### 4.2 The LEARN job (`learn_batch`, fixed cron)

One new job, registered next to `metrics_batch`. It runs *after* the engagement polls and metrics job so the ledger is freshest (`engagement_poll` :05, `metrics_batch` :10, **`learn_batch` :20**).

Add `from app.jobs.learn_job import run_learn_job` to `main.py`'s job imports (beside `run_metrics_job`), then register inside `_build_scheduler()`. `tz` and `misfire` are already in scope there (`main.py:43-48`):

```python
# app/main.py — added inside _build_scheduler(), mirroring the metrics_batch block (main.py:78-86)
    if settings.learn_enabled:
        sched.add_job(
            run_learn_job,
            CronTrigger(minute="20", timezone=tz),
            id="learn_batch",
            replace_existing=True,
            misfire_grace_time=misfire,
            coalesce=True,
            max_instances=1,
        )
```

```python
# app/jobs/learn_job.py — mirrors metrics_job.py's per-account loop shape
import logging

from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.services.champion_challenger_service import (
    evaluate_promotion, evaluate_regression,
)
from app.services.pipeline_spec_repository import PipelineSpecRepository, promote_challenger
from app.services.spec_rewrite_service import propose_and_stage_challenger
from app.services.spec_rollback import rollback_to_parent

logger = logging.getLogger(__name__)


def run_learn_job() -> dict:
    """LEARN tick: per active account, (1) auto-rollback a hard-regressed champion,
    (2) optionally auto-promote an improved challenger, (3) stage a challenger if none
    exists. Pure RavenDB reads/writes — NO X-API calls."""
    if not settings.learn_enabled:
        return {"skipped": "learn_disabled"}
    accounts = AccountRepository().list_active()
    repo = PipelineSpecRepository()
    actions: list[dict] = []
    for acc in accounts:
        aid = acc.account_id
        champ = repo.load(aid, "champion")
        if champ is None:
            continue  # no spec yet (pre-seed) → nothing to learn from

        # (1) auto-rollback on hard regression (the ONE automatic mutation)
        if settings.learn_auto_rollback_enabled and champ.parent_hash:
            reg = evaluate_regression(
                aid, current_hash=champ.version_hash, parent_hash=champ.parent_hash,
                min_window=settings.learn_rollback_min_window,
                hard_drop=settings.learn_rollback_hard_drop,
            )
            if reg.regressed:
                restored = rollback_to_parent(aid, parent_hash=champ.parent_hash, repo=repo)
                actions.append({"account_id": aid, "action": "rollback", "drop": reg.drop,
                                "ok": restored is not None})
                continue  # rolled back this tick; do not also stage/promote on the same pass

        # (2) optional auto-promote (default OFF → manual)
        challenger = repo.load(aid, "challenger")
        if challenger is not None and settings.learn_auto_promote_enabled:
            verdict = evaluate_promotion(
                aid, champion_hash=champ.version_hash, challenger_hash=challenger.version_hash,
                min_window=settings.learn_promote_min_window,
                min_improvement=settings.learn_promote_min_improvement,
            )
            if verdict.eligible:
                promote_challenger(aid, repo=repo)   # doc 04's forward primitive
                actions.append({"account_id": aid, "action": "promote", "delta": verdict.delta})
                continue

        # (3) stage a challenger when there is none to compare against
        if challenger is None and settings.learn_propose_challenger_enabled:
            staged = propose_and_stage_challenger(aid, repo=repo)
            actions.append({"account_id": aid, "action": "stage_challenger",
                            "staged": staged is not None})

    logger.info("learn_job: %d accounts, %d actions", len(accounts), len(actions))
    return {"accounts": len(accounts), "actions": actions, "status": "ok"}
```

> **Decision Defense — one fixed cron job, not a reconcile loop or a per-account timer.** The architecture explicitly rejects the Reconciler (no poll loop). LEARN is naturally batch: it reads aggregate reward, which only changes when the engagement jobs refresh the ledger (hourly-ish). A single `:20` cron after `metrics_batch` :10 gives it the freshest ledger with zero new infrastructure — the exact pattern `metrics_job` already follows. Per-account timers would be the deferred per-agent scheduling we are explicitly not building (§4.3).

### 4.3 DEFERRED: per-agent scheduling (stated plainly)

**Per-account / per-agent scheduling is DEFERRED.** Today there is one `scheduled_posting` cron for *all* active accounts (`run_interval_job` loops over `Orchestrator().run_tick()` which loops over active accounts — verified `interval_job.py:37`, `orchestrator.py:56-73`). Giving each account its own cadence, its own challenger ratio, or its own LEARN window would require either N APScheduler jobs (one per account, dynamically added/removed as accounts come and go) or an in-doc per-account schedule the scheduler reads — both are real subsystems with their own lifecycle, lock, and teardown concerns. With **one** account today it is pure speculation (CLAUDE.md §2). The trivial future path, recorded so it is not lost: make `challenger_slot_every` and the LEARN windows **per-account fields on the spec/soul** and read them inside the existing single jobs (`_slot_spec_status` already runs per `run_tick`; the LEARN loop is already per-account). No new scheduler is ever needed; the fixed jobs stay fixed and read per-account knobs. We do not build that now.

---

## 5. `spec_rewrite_service` — propose a NEW spec (catalog tools only)

The self-rewrite proposes a *different* `PipelineSpecDocument` and stages it as a challenger. It **only rewires + reconfigures existing catalog tools**; the doc `05` validator is the hard wall that makes "only existing tools" true, not a promise.

### 5.1 The contract: validator-gated, never raw

```python
# app/services/spec_rewrite_service.py
from app.core.config import settings
from app.infrastructure.claude_client import get_claude_client  # §5.4 (LLM path) + §5.3 (soul)
from app.models.pipeline_spec import PipelineSpecDocument
from app.pipeline.spec.catalog import get_tool_catalog          # doc 03 — the ToolCatalog OBJECT (.get/__contains__)
from app.pipeline.spec.validator import validate_spec           # doc 05
from app.services.account_repository import AccountRepository    # §5.3 soul self-rewrite
from app.services.pipeline_spec_repository import PipelineSpecRepository
from app.services.pipeline_version_service import compute_pipeline_hash  # §5.1 identity guard


def propose_and_stage_challenger(
    account_id: str,
    *,
    repo: PipelineSpecRepository | None = None,
) -> PipelineSpecDocument | None:
    """Build a challenger from the current champion, validate it with the SAME gate
    the runner uses, and stage it as status='challenger'. Returns the staged spec, or
    None if no valid distinct proposal was produced (nothing is written on failure).
    Only needs account_id — the champion spec (not the AccountDocument) is the input."""
    repo = repo or PipelineSpecRepository()
    champion = repo.load(account_id, "champion") or PipelineSpecDocument(account_id=account_id)
    catalog = get_tool_catalog()   # doc 03's ToolCatalog wrapper — validate_spec(doc, catalog) wants .get()/in, NOT the raw build_tool_catalog() list

    proposal = _propose_spec(champion, catalog)        # §5.2 (deterministic) or §5.4 (LLM)
    if proposal is None:
        return None

    # Identity guard: a proposal byte-identical to the champion is not a challenger.
    # compute_pipeline_hash hashes ONLY the steps tree (doc 04 §5a), so a top_n change
    # always yields a different hash; champion.version_hash may be None pre-first-save,
    # so fall back to hashing the champion's steps directly.
    if compute_pipeline_hash(proposal) == (champion.version_hash or compute_pipeline_hash(champion)):
        return None

    # THE GATE — same validator the runner runs (doc 05). unknown_tool / non-literal
    # config / dangling reads / bypassed invariants all reject here, before staging.
    report = validate_spec(proposal, catalog)
    if not report.ok:
        return None  # caller logs report.codes(); we never stage an invalid spec

    proposal.account_id = account_id
    proposal.status = "challenger"
    proposal.parent_hash = champion.version_hash       # lineage for promote/rollback
    proposal.version_hash = None                        # force a fresh challenger version on save
    repo.save(proposal)                                 # PUT pipelinespecs/{aid}-challenger (doc 04)
    return proposal
```

> **Decision Defense — validate with the runner's exact `validate_spec`, not a bespoke "rewrite checker".** The brief is emphatic: self-rewrite is "gated by the SAME validator". Doc `05`'s `validate_spec` already enforces every property a safe spec needs — `unknown_tool` (R1) makes "only existing catalog tools" structurally impossible to violate, `config_*` (R2) rejects setting a non-`literal`/`wired`/`injected` knob, and the **safety/publish invariants are detected purely from artifact writes (CC-2, no flag)**: R7 (`missing_safety_invariant`) requires at least one leaf whose catalog tool writes `SAFETY_VERDICT`, and R6 (`no_terminal_published`/`step_after_publish`) requires exactly one **terminal** leaf writing `PUBLISHED_POST`. So the guardian-bearing `compose_until_safe` and the idempotent `publish_post` cannot be removed or bypassed. A second validator would risk drifting from the runner's and letting a spec pass rewrite-check but fail at runtime. One gate, one truth.
>
> **The gate presupposes a baseline that already satisfies CC-2.** R6/R7 pass only because the champion the proposer clones is the **10-leaf baseline** (CC-6): doc `04`'s `default_pipeline_spec`/`spec_from_runbook` emits the 8 SENSE leaves **plus** `compose_until_safe` (`llm.compose_until_safe`, writes `SAFETY_VERDICT`) and `publish_post` (`data.publish_post`, terminal, writes `PUBLISHED_POST`) — the two ACT-tail tools doc `06` adds to `ArtifactKey`/`ARTIFACTS` and the catalog. The deterministic proposer (§5.2) only nudges one `literal` knob on a SENSE leaf and never touches those two ACT leaves, so a clone of a valid champion is structurally guaranteed to keep both invariant writers and re-pass R6/R7. (Corollary: if docs `04`/`06` have not yet landed and the champion lacks the ACT tail, the champion itself fails R6/R7 and §5.1's gate rejects the clone — an upstream baseline-validity dependency, not a proposer defect; see §5.2's `store_key` note for the same fail-closed posture.)

### 5.2 The DEFAULT proposer: deterministic single-knob tweak

`learn_use_builder_llm` defaults **off**. The default proposer makes the smallest possible *legal* change: nudge ONE `literal`-origin config knob on ONE specific leaf. Per doc `03`, the only truly free literal knobs today are two integers — `top_n` (on `deterministic.reference_rank`) and `max_results_per_query` (on `data.search_fetch`).

**Which leaf — resolved.** `deterministic.reference_rank` is wired into **two** leaves (`rank_external_references` and `rank_own_posts`, per doc `04` §7 `STEP_TOOL_MAP`/`STEP_CONFIG`), so targeting by `tool_id` is ambiguous. The proposer tunes the **`rank_external_references`** leaf, addressed by its **step `id`** (not its `tool_id`). That ranker decides which external references feed `compose_until_safe`, so its `top_n` has the most direct effect on what gets composed — the most interpretable single-variable A/B. `_find_leaf` matches on `id`:

```python
def _find_leaf(spec: PipelineSpecDocument, *, step_id: str):
    """Depth-first walk of the steps tree; return the first StepSpec whose id == step_id,
    or None. Recurses into CompositeSpec.children (rank_external_references is nested under
    summarize_for_compose.analyze_external_references, doc 04 §3c)."""
    def walk(nodes):
        for n in nodes:
            if getattr(n, "kind", None) == "step" and n.id == step_id:
                return n
            children = getattr(n, "children", None)
            if children:
                hit = walk(children)
                if hit is not None:
                    return hit
        return None
    return walk(spec.steps)


def _propose_spec(champion, catalog):
    """Dispatch: the LLM proposer (§5.4) when learn_use_builder_llm is on, else the
    deterministic knob-tweak below. Returns a NEW PipelineSpecDocument or None."""
    if settings.learn_use_builder_llm:
        return _propose_spec_llm(champion, catalog)        # §5.4
    # ── DEFAULT: clone the champion, bump the `rank_external_references` leaf's top_n
    #    by one rung on a fixed ladder. None if that leaf is absent (a heavily-rewritten
    #    spec that dropped the external ranker). ──
    proposal = PipelineSpecDocument.model_validate(champion.model_dump())  # deep clone
    leaf = _find_leaf(proposal, step_id="rank_external_references")
    if leaf is None:
        return None
    ladder = [8, 10, 12, 15]
    cur = int(leaf.config.get("top_n", 10))
    leaf.config["top_n"] = ladder[(ladder.index(cur) + 1) % len(ladder)] if cur in ladder else 10
    return proposal
```

The cloned leaf's `config` retains whatever wired/injected keys the baseline carried (e.g. `store_key`); the proposer only overwrites the one `literal` integer, so the proposal validates exactly when the champion does. (If docs `03`/`04`/`05` have not yet reconciled `store_key`/`source` out of seed `config` into compile-time wiring — a known sibling-doc reconciliation, doc `04` §7 / doc `05` R2 — then the *champion itself* fails `validate_spec` and §5.1's gate rejects the clone too; that is an upstream baseline-validity dependency, not a defect in this proposer. §5.1 never stages an unvalidatable spec.)

> **Decision Defense — why a tiny deterministic tweak is the default, with the LLM opt-in.** Two reasons. (1) *Safety/cost:* a deterministic single-knob change is guaranteed to validate (it only touches a `literal` knob within range) and costs zero Claude tokens, so the LEARN job is free to run every hour. (2) *Honesty about the surface:* doc `03` proved the LLM-proposable surface today is "tool selection + ordering + two integers". Until more `literal` knobs exist, an LLM rewrite would mostly reorder/select tools — high blast radius for a one-account system with ~tens of posts. The deterministic ladder gives a clean, attributable A/B (champion `top_n=10` vs challenger `top_n=12`) whose reward delta is interpretable. The LLM path (§5.4) is wired and validator-gated for when the catalog grows; it is just not the default.

### 5.3 Soul self-rewrite reuses `voice_version_service`

The soul (personality / posting_prompt / contrast_patterns / punctuation_rules) is rewritten on the **account**, not the spec, and it versions through the **existing** soul machinery — no new versioning. A proposed soul edit is applied to a loaded `AccountDocument` and saved; `AccountRepository.save` already calls `bump_voice_version_if_needed` (verified `account_repository.py:18` import + `:115-116` call), which hashes via `compute_voice_hash` and archives a `VoiceRevisionDocument`. So soul self-rewrite is "edit the soul fields → `repo.save(account)`" and the version/archive happen for free:

```python
def propose_and_apply_soul_rewrite(account, *, repo=None, claude=None) -> bool:
    """Propose a soul edit (personality/contrast tweak) and apply it. Versioning +
    revision archive are handled by AccountRepository.save → bump_voice_version_if_needed
    (soul plan). Returns True if a change was applied (version bumped), else False."""
    repo = repo or AccountRepository()
    before = account.voice_version_hash
    _apply_soul_proposal(account, claude)          # mutates soul fields in place (below)
    repo.save(account)                              # bumps voice_version_* + archives if soul changed
    return account.voice_version_hash != before
```

`_apply_soul_proposal` mutates the loaded account's soul fields in place; it is the soul analogue of `_propose_spec`. With `learn_use_builder_llm=False` (default) it is a no-op stub that returns without changing anything (there is no safe *deterministic* soul nudge — unlike a numeric `top_n` ladder, "tweak the personality" has no single-variable ladder), so `propose_and_apply_soul_rewrite` returns `False`. With the flag on, it asks Claude for a revised soul-field set via the §5.4 client and assigns the returned fields onto `account.soul`:

```python
def _apply_soul_proposal(account, claude) -> None:
    """Default (learn_use_builder_llm off): no-op — no deterministic soul ladder exists.
    LLM on: ask Claude for revised personality/posting_prompt/contrast_patterns and
    assign them onto account.soul; AccountRepository.save versions the change."""
    if not settings.learn_use_builder_llm:
        return
    claude = claude or get_claude_client()
    if not claude.enabled:
        return
    proposal = claude.messages_json_dict(
        system=_render_soul_rewrite_system_prompt(account),   # describes the soul-field schema
        user=_render_current_soul(account),                   # the account's current soul fields
        max_tokens=2048,
    )
    if not proposal:
        return
    for field in ("personality", "posting_prompt", "contrast_patterns", "punctuation_rules"):
        if field in proposal:
            setattr(account.soul, field, proposal[field])     # soul fields live on account.soul
```

> **Soul rewrite is a library call (builder/endpoint), NOT an automatic LEARN-job action — and that is deliberate.** `run_learn_job` (§4.2) calls *only* `propose_and_stage_challenger`; it never calls `propose_and_apply_soul_rewrite`. Reason: a staged pipeline *challenger* runs on 1-in-N slots and is A/B-isolated before promotion, but the soul has **no challenger staging doc** (defended below) — editing it changes the live soul for **every** post immediately, with no isolation. Auto-firing a soul edit each LEARN tick would mutate production voice continuously with no operator in the loop. So `propose_and_apply_soul_rewrite` is exposed for the **builder/agent endpoint (doc `10`)** and the dashboard to call on explicit human action; the autonomous LEARN loop does not invoke it. This is why §3.1's `score_soul_hash` exists (so the dashboard can show "which soul version scored better") while the job stays pipeline-only. The function is wired and version-safe; it is simply not on the unattended cron path.

> **Decision Defense — soul rewrite does NOT mirror the pipeline-spec champion/challenger machinery.** The soul already has full versioning + an immutable revision archive (`voice_revision.py` + `voice_version_service.py`), and the ledger already stamps `soul_hash` on every post, so §3.1's `score_soul_hash` can A/B soul versions off the same rows. What the soul lacks is a *champion/challenger staging doc* — and it does not need one: there is exactly one live soul per account (it lives on the account), and edits are reversible by re-applying an archived `VoiceRevisionDocument`'s fields the same way `rollback_to_parent` re-applies a pipeline revision. Building a parallel soul-challenger doc would duplicate the spec machinery for a value that is already versioned in place. Reuse `voice_version_service`; A/B by `soul_hash`; roll back by re-applying a revision. This is the elegant, non-duplicative option the brief asks for ("Soul self-rewrite reuses voice_version_service").

### 5.4 The optional builder-LLM path (wired, gated, off by default)

When `learn_use_builder_llm` is on, `_propose_spec` (or `_apply_soul_proposal`) asks Claude for a JSON proposal, then runs it through the *same* validator. The catalog (doc `03`) is rendered into the prompt so the model can only reference real tools and `literal` knobs:

```python
def _propose_spec_llm(champion, catalog):
    claude = get_claude_client()
    if not claude.enabled:
        return None
    system = _render_builder_system_prompt(catalog)   # lists tool_ids + proposable_params only
    user = _render_current_spec(champion)
    raw = claude.messages_json_dict(system=system, user=user, max_tokens=2048)  # verified API
    if raw is None:
        return None
    try:
        return PipelineSpecDocument.model_validate({**raw, "account_id": champion.account_id})
    except Exception:
        return None   # malformed JSON → no proposal; never stage unvalidated data
```

The returned object is *still* fed to `validate_spec` in `propose_and_stage_challenger` (§5.1) — the LLM never bypasses the gate. A hallucinated `tool_id` produces `unknown_tool` and the proposal is dropped. **The LLM can only ever rewire/reconfigure existing tools because the validator makes anything else un-stageable.**

The four prompt-render helpers (`_render_builder_system_prompt`, `_render_current_spec`, `_render_soul_rewrite_system_prompt`, `_render_current_soul`) are thin, dependency-free `str`-builders local to `spec_rewrite_service.py`:
- `_render_builder_system_prompt(catalog)` iterates `catalog.all()` (doc `03`'s `ToolCatalog.all() -> list[ToolCatalogDocument]`, `03` §lookup-class) and enumerates each tool's `tool_id`, `purpose`, and `proposable_params` (the `config_origin == "literal"` knobs only — a property on `ToolCatalogDocument`, doc `03`), plus the required `PipelineSpecDocument` JSON shape (doc `04` §3b: `steps` is a list of `{"kind":"step", "id","tool_id","reads","writes","config","purpose"}` leaves and `{"kind":"parallel"|"chain", "id","children","purpose"}` composites). It instructs the model to return ONLY that JSON. No tool internals, no injected-dep names.
- `_render_current_spec(champion)` is `json.dumps(champion.model_dump(mode="json"), indent=2)` of the champion's `steps` — the starting point the model edits.
- `_render_soul_rewrite_system_prompt(account)` / `_render_current_soul(account)` are the soul analogues: the former lists the four editable soul fields and asks for a JSON object keyed by them; the latter dumps the account's current soul-field values. These mirror the spec renderers exactly, swapping the spec schema for the soul-field schema.

Because the model output is parsed by `messages_json_dict` (which extracts the first `{...}` block and returns `dict | None`, verified `claude_client.py:77-88`) and then `PipelineSpecDocument.model_validate(...)`, any non-JSON or schema-violating output yields `None` and stages nothing — the validator gate (§5.1) is the only path to a written challenger.

---

## 6. No DB transactions — the partial-write window, stated honestly

RavenDB has no multi-doc transactions; the HTTP client's `put_document` is an unconditional PUT with no If-Match/CAS (verified `app/infrastructure/ravendb_http.py:103-110`; doc `02`/`04`/`08` all confirm). Every mutating operation in this doc is therefore a **short sequence of plain puts**, ordered fail-safe. The two sequences:

**Promotion** (doc `04`'s `promote_challenger`, called here): validate → write new champion (PUT #1) → delete challenger doc (best-effort). Doc `04` §6c already documents this window; we restate the consequence for *this* doc's callers: there is exactly **one** mutating write to the champion (PUT #1, not split), so the champion is never half-written. Between PUT #1 and the challenger delete, both `pipelinespecs/{aid}` and `pipelinespecs/{aid}-challenger` describe the same steps; the runner reads **only** the champion (`spec_status` defaults to champion, and a challenger slot with a now-deleted challenger falls back to champion — §4.1), so execution is never ambiguous. A crash *before* PUT #1 leaves the old champion live (fail-safe).

**Rollback** (`rollback_to_parent`, §3.5): load parent revision → write restored champion (PUT, single). One mutating write. A crash before it leaves the regressed champion live — which is safe because the next `learn_batch` tick re-detects the regression and retries. There is no second doc to coordinate, so there is no cross-doc window at all.

**Validate-then-activate ordering is the rule everywhere.** Promotion validates (doc `04` calls `compile_spec`) *before* the activating PUT; self-rewrite validates (`validate_spec`) *before* the staging PUT. We never activate an unexecutable spec, because validation has no side effects and always precedes the only mutating write.

> **Decision Defense — why no CAS is actually fine here.** CAS protects against *concurrent writers* racing on the same doc. The only writer of `pipelinespecs/{aid}` is the LEARN job (`max_instances=1`, `coalesce=True` — verified the pattern on every job in `main.py`) plus the occasional manual promote endpoint. The LEARN cron and a manual promote could in principle overlap, but both go through `repo.save`/`promote_challenger`, both are last-writer-wins on a *single* doc, and the worst case is a redundant version bump (a new `v{n}` revision identical in steps), which the version service de-dupes anyway (`bump_pipeline_version_if_needed` returns early when the hash is unchanged — verified `pipeline_version_service.py` mirror of `voice_version_service.py:72`). No lost spec, no corrupt doc, no half-promotion. CAS would add a retry loop for a race whose worst outcome is a no-op bump. This is the same last-writer-wins reasoning doc `02` used for the ledger and doc `08` for the trace.

---

## 7. Decision Defense (cross-cutting, non-obvious choices)

**Why is rollback the only automatic mutation, and promotion manual?**
Promotion *adds* a hopeful variant the operator chose to stage and that the metrics now favor; getting it slightly wrong is cheap and reversible (the challenger was already running on 1-in-N slots, so it is battle-tested before promotion). Rollback *undoes an operator's standing choice* under evidence it is actively hurting — that is a safety action that must not wait for a human to notice. So the asymmetry: rollback auto-fires on a *large* drop (0.05) with a sample-size gate; promotion only *recommends* on a *small* win (0.02) and waits for a human, unless the operator opts into `learn_auto_promote_enabled`. This is precisely the brief's "manual-promote with auto-rollback on hard regression."

**Why does LEARN ride the existing fixed cron set instead of reacting to each post?**
Reward only changes when the engagement jobs refresh the ledger (hourly-ish, doc `01`/`02`), and the architecture forbids a reconcile/poll loop. A per-post LEARN trigger would recompute aggregates that haven't moved (most posts are `None`/unpolled for hours) and risk re-entrancy with the posting tick. One `:20` cron after `metrics_batch` :10 reads the freshest ledger once per hour with zero new infrastructure and zero X-API calls — the same discipline `metrics_job` already follows, and the same cost-incident avoidance `MEMORY.md` demands.

**Why aggregate by `pipeline_hash` AND `soul_hash` separately, not a combined key?**
Pipeline and soul version *independently* (pipeline on `pipelinespecs/*`, soul on the account), and a post's reward is attributable to *both*. Grouping by a combined `(pipeline_hash, soul_hash)` key would fragment the sample — with ~tens of posts, every combined bucket would fall below the `min_window` and nothing would ever promote. Scoring each axis independently (a champion/challenger A/B holds the soul roughly constant within the window, and vice versa) keeps each comparison's sample size usable. The ledger carries both top-level fields precisely so each axis is a one-query group-by.

**Why a `challenger_slot_every` ratio instead of a 50/50 split?**
A challenger is unproven. Running it on half of all posts doubles the exposure of an account's audience to an untested pipeline. 1-in-N (default 4) keeps the champion dominant — three of four posts stay on the proven spec — while the challenger still earns a steady, attributable trickle of reward rows. The ratio is a tunable knob, not a hardcoded constant, so an operator who wants faster learning can lower it.

**Why is the deterministic knob-tweak the default proposer rather than the LLM?**
Honesty about the surface (doc `03`): today the LLM-proposable knobs are two integers plus tool selection/ordering. A deterministic `top_n` ladder produces a clean, single-variable A/B whose reward delta is interpretable and whose validity is guaranteed (it only moves a `literal` knob in range). The LLM path is fully wired and validator-gated for when the catalog grows more knobs, but defaulting to it now would mostly reorder tools — high variance for a one-account system — and spend tokens on every LEARN tick. Simplicity-first (CLAUDE.md): the smallest legal change that yields a measurable signal.

---

## 8. Definition of Done (per slice)

**Aggregation + decision rules (`champion_challenger_service`)**
- `score_pipeline_hash(h, account_id=...)` returns a `SpecScore` whose `avg_reward` is the mean of **non-`None`** ledger `reward`s for `h`, `n_scored` counts only those, and `avg_reward is None` when `n_scored == 0` (never `0.0`). A unit test feeds mixed `reward`/`None` rows and asserts the `None`s are excluded.
- `evaluate_promotion(...)` returns `insufficient_window` when either arm has `< min_window` scored rows; `improved` (eligible) only when `delta >= min_improvement`; `no_improvement` otherwise. Each branch has a test.
- `evaluate_regression(...)` returns `no_parent` when `parent_hash` is falsy; `insufficient_window` below the gate; `hard_regression` only when `drop >= hard_drop`; `stable` otherwise. Each branch has a test.
- `score_soul_hash(soul_hash, account_id=...)` mirrors `score_pipeline_hash` but reads via the new `OutcomeLedgerRepository.list_for_soul_hash` (which filters the ledger on the `soul_hash` column); a unit test asserts it returns the soul-keyed rows and excludes `None` rewards exactly as `score_pipeline_hash` does.

**Rollback (`spec_rollback`)**
- `rollback_to_parent(aid, parent_hash=h)` rebuilds a champion from the revision whose `version_hash == h`, sets its `parent_hash` to the outgoing (regressed) champion's hash, and `save`s it (one PUT). Returns `None` (no write) when no revision matches `h`.
- A unit test with a fake `PipelineRevisionRepository`/`PipelineSpecRepository` asserts the restored `steps` equal the parent revision's `steps` and exactly one `save` fired.
- The rollback **increments** the version sequence past the outgoing champion (`restored.version_seq == current.version_seq + 1` after `save`), and does **not** reset to `v1` or overwrite the original `v1` revision — a test seeds a champion at `v4` and asserts the rollback writes `v5`, archiving a new revision while the `v1`/`v3` revisions are untouched.

**Self-rewrite (`spec_rewrite_service`)**
- `propose_and_stage_challenger(aid)` stages a `status="challenger"` spec with `parent_hash = champion.version_hash` **only** when the proposal both differs from the champion (distinct `compute_pipeline_hash`) and passes `validate_spec`; otherwise it writes nothing and returns `None`.
- A test injecting a proposal with `tool_id="data.does_not_exist"` asserts `"unknown_tool" in validate_spec(proposal, catalog).codes()` and **no** `pipelinespecs/{aid}-challenger` doc is written (the fake `repo.save` records zero calls).
- The deterministic proposer (`learn_use_builder_llm=False`) bumps the `rank_external_references` leaf's `top_n` one rung and produces a spec whose `compute_pipeline_hash` differs from the champion's (the knob actually changed); a champion whose external ranker leaf is absent yields `None` (no proposal).
- Soul: with `learn_use_builder_llm=True` and a stubbed `claude` returning a changed `personality`, `propose_and_apply_soul_rewrite(account, claude=fake)` mutates that soul field and `repo.save`s; a test asserts it returns `True`, `account.voice_version_hash` changed, and a `VoiceRevisionDocument` was archived (via the soul service, not re-implemented here). With the flag off, `_apply_soul_proposal` is a no-op, so although `repo.save` is still called, `bump_voice_version_if_needed` early-returns on the unchanged soul (no new revision, hash unchanged) and the function returns `False` — also asserted. `run_learn_job` never calls it (soul rewrite is manual, §5.3).

**Routing + job (`learn_job`, `main.py`, runner [`build_tick_context` + `_run_account_pipeline`], context)**
- `_build_scheduler()` registers `learn_batch` at `CronTrigger(minute="20", timezone=tz)` with `replace_existing=True, misfire_grace_time=misfire, coalesce=True, max_instances=1` when `settings.learn_enabled`; not registered when disabled. (Mirror the `metrics_batch` block, `main.py:78-86`.)
- `run_learn_job()` makes **zero** X-API calls (grep the diff: no `tw.`/`get_posts_metrics`/`requests`), loops active accounts, and for each performs rollback → optional auto-promote → stage-challenger in that order, short-circuiting after a mutation.
- `_slot_spec_status(slot, mode)` returns `"challenger"` on 1-in-`challenger_slot_every` slots and `"champion"` otherwise, as a pure function of its `slot` argument; it returns `"champion"` for any non-`"scheduled"` mode (force-post). It does **not** call `current_interval_slot_key()` itself — `build_tick_context` passes the slot it already computed (`runner.py:74`), so there is one clock read per tick and no drift.
- `build_tick_context` sets `ctx.spec_status = _slot_spec_status(slot, mode)`; `interval_job.py` and `orchestrator.run_tick` are **unchanged** (no `spec_status` kwarg threads through them).
- `_run_account_pipeline` loads the spec via `_load_spec_for_status(aid, ctx.spec_status, PipelineSpecRepository())`; a challenger slot with **no** staged challenger falls back to `load_or_default(aid)` (champion or baseline) and posts normally — the doc `07`/`04` load semantics are otherwise unchanged. There is no `load_active_spec`/`SEED_SPEC` symbol anywhere (**CC-5**).
- `TickContext.spec_status` defaults `"champion"`, so every existing call site (tests constructing a `TickContext` directly) and the force-post path are unaffected.

**No-transaction safety (§6)**
- Promotion never produces a half-written champion (single PUT #1); a simulated crash after PUT #1 but before the challenger delete leaves a harmless duplicate, and the runner reads only the champion.
- Rollback is a single PUT; a simulated failure before it leaves the regressed champion live, and a re-run of `evaluate_regression` still flags it (idempotent retry).
- A redundant promote/rollback with unchanged `steps` produces **no** new revision (the version service early-returns on an unchanged hash).

**Global**
- `python -m py_compile` clean across the four new service/job files (`champion_challenger_service.py`, `spec_rewrite_service.py`, `learn_job.py`, `spec_rollback.py`) and the five changed files (`main.py`, `config.py`, `interval/runner.py`, `interval/context.py`, `outcome_ledger_repository.py`).
- `pytest tests/unit/test_champion_challenger_service.py tests/unit/test_spec_rewrite_service.py` green; full `pytest` green (no existing test asserts on the new optional `TickContext.spec_status` / `Settings.learn_*` fields — all additive with defaults; `interval_job.py` and `orchestrator.py` are untouched, so their tests are unaffected).
- `docker compose up -d --build` healthy; with `learn_enabled=true` and a seeded challenger, a `:20` LEARN tick runs without error and, given a staged challenger and ≥`min_window` scored posts on each arm, either records a `promote` recommendation (manual) or, with `learn_auto_rollback_enabled` and a hard-regressed champion, performs a rollback and writes a new champion revision.

---

## 9. Sibling-doc references (shared types owned elsewhere)

- **doc `01` (MEASURE):** owns `post_reward` / `account_avg_reward` / the `[0,1]` scale + `None`-means-insufficient contract. §3 consumes `reward` off ledger rows on that exact scale; thresholds (0.02 / 0.05) are expressed in those units.
- **doc `02` (ledger + attribution):** owns `OutcomeLedgerDocument` (`pipeline_hash`, `soul_hash`, `reward`, `recorded_at`) and `OutcomeLedgerRepository.list_for_pipeline_hash`. §3.1's pipeline aggregation is one call per hash against this repo. The `run_id`/`pipeline_hash` join that makes attribution work is owned by doc `02` (the `PostCreationMetrics` field add + the publish-time stamp from `load_or_default(account_id).version_hash`) and doc `07` (capturing the *walked* spec's `version_hash` and threading it to `publish_post`). **This doc adds one method to doc `02`'s repo — `list_for_soul_hash` (§3.1) — a 6-line mirror of `list_for_pipeline_hash`; everything else in doc `02` is consumed read-only.**
- **doc `03` (tool catalog):** owns `build_tool_catalog() -> list`, `get_tool_catalog() -> ToolCatalog` (the lookup object), `ToolCatalog.all()`/`.get()`/`in`, `ToolCatalogDocument.proposable_params` (the `config_origin == "literal"` knobs), and `config_origin`. §5's proposer takes the **`ToolCatalog` object** (`get_tool_catalog()`) so it can be passed straight to `validate_spec`; the LLM prompt renders `.all()` + `.proposable_params` only.
- **doc `04` (spec model + versioning + promotion):** owns `PipelineSpecDocument`, the `status`/`parent_hash`/`version_*` lifecycle, `PipelineSpecRepository` (`load`/`load_or_default`/`save`), `PipelineRevisionRepository.list_for_account`, `compute_pipeline_hash`/`bump_pipeline_version_if_needed`, and the forward `promote_challenger` put-sequence. This doc *drives* those; it adds only the rollback put (§3.5) and the decision rules (§3).
- **doc `05` (validator + compiler):** owns `validate_spec` (the gate §5.1 reuses verbatim) and `compile_spec` (which `promote_challenger` calls to refuse an unexecutable promotion). The self-rewrite is safe *because* this validator rejects `unknown_tool` and bypassed invariants (R1/R6/R7).
- **doc `07` (interpreter wiring):** owns `_run_account_pipeline`, the once-per-run spec load (`PipelineSpecRepository().load_or_default(aid)`, §2.4 `runner.py:129`), and the spec-walk. **There is no `load_active_spec` and no `SEED_SPEC`** (**CC-5** — doc `04`'s §6b-bis `load_active_spec` and doc `07`'s prose are superseded; the entry point is `load_or_default`). §4.1's only runner-load change is replacing that one line with `_load_spec_for_status(aid, ctx.spec_status, repo)`, which uses doc `04`'s `load`/`load_or_default` exclusively. Doc `07` also owns capturing the **walked** `spec.version_hash` and handing it to `publish_post` as `pipeline_hash` (**CC-3**); §4.1 relies on that so each arm's posts attribute to the spec that actually ran — a challenger slot stamps the challenger's hash, never `load_or_default`'s champion hash.
- **soul-pipeline `05-versioning.md`:** owns `voice_version_service`. §5.3's soul self-rewrite reuses it verbatim; no soul-side versioning is added here.

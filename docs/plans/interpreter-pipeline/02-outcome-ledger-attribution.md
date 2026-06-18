# Task 02 — Outcome Ledger + Attribution Join

> **Status:** Ready to implement. Authored cold against live code (every API verified against the files cited, not memory).
> **Scope:** Backend only. (a) Close the ONE attribution gap so every posted tweet carries `run_id` + `pipeline_hash`; (b) add a plain `OutcomeLedgerDocument` that projects each post's reward + raw metrics, stamped at publish and updated as engagement arrives.
> **Target project:** `SocialMediaAutonomousAgents/backend/`.
> **DB reality:** One account today (`JohnJames_News`). `creation_metrics` / `run_id` are optional and additive, so this is a non-breaking change — old `TrackedPostDocument`s simply lack the new fields.

> **Cross-refs (shared types defined elsewhere — do NOT redefine here):**
> - `pipeline_hash` (the SHA256 digest of the active `PipelineSpecDocument`) is produced by **doc 04 — Pipeline Spec Model + Versioning** as `PipelineSpecDocument.version_hash` (`compute_pipeline_hash`, doc 04 §5a). It lives on a **separate** `pipelinespecs/{account_id}` document, **NOT** on the account — there is no `account.pipeline_version_hash` accessor and none is added by any doc (**CC-3**). The single load API is `PipelineSpecRepository().load_or_default(account_id, kind="post")` (**CC-5**), returning the **champion** spec (or the seeded default); there is no `load_active_spec` free function and no `SEED_SPEC` module constant. **Pre-06/07** (no `ActLive`/deps yet) this task READS the value directly via `PipelineSpecRepository().load_or_default(account_id, kind="post").version_hash` (doc 04 §6b). **Post-06/07** the loaded/walked spec's `version_hash` is threaded by doc 07 into `deps.live.pipeline_hash` (**CC-3, CC-7**) and `publish_post` reads it from there — it does **not** re-load the repo. See §6 "Decision Defense → pipeline_hash source of truth" for both forms and the graceful-default behavior when no spec doc exists yet.
> - `run_id` is generated today in `run_account_pipeline` (`interval/runner.py:141`). This task threads it down to `finalize_post`; no new generation.
>
> **Sibling-doc numbering (verified against the final filenames in this folder):** the Pipeline Spec model lives in **doc 04** (`04-pipeline-spec-and-versioning.md`); the reward function is **doc 01**; the champion/challenger evaluator that consumes this ledger is **doc 09**; the ACT-path rewrite that relocates the `creation_metrics` stamping site is **docs 06/07**; the full-fidelity step trace is **doc 08**. Earlier drafts of this doc referred to the spec model as "doc 01" — every such reference has been corrected to **doc 04**.
>
> **Sequencing gate (load-bearing — read before implementing):** this doc owns the `PostCreationMetrics` model edit (§3.1) AND the canonical attribution-stamping site. Docs 06/07 **delete** the inline `creation_metrics` construction at `runner.py:412-424` and move it into the new `publish_post` tool, which doc 06 §5.2 leaves with a `# when 08 lands` placeholder for `run_id`/`pipeline_hash`. **This doc (02) is that owner.** Therefore: §3.1 (the two new model fields) MUST be merged before docs 06/07 land, or `PostCreationMetrics(run_id=...)` raises an "extra field" error. The stamping *code* has two homes depending on order — see §3.4, which gives BOTH the pre-06/07 form (edit `runner.py:412-424`) and the post-06/07 form (edit `publish_post.run`). Apply whichever matches the tree you are on; they stamp the identical two values.

---

## 1. Why this change

Attribution today is *almost* complete and *almost* useless:

| What we record | Where | Joinable to a run? | Joinable to a pipeline version? |
|---|---|---|---|
| `voice_version_hash/seq/label` | `PostCreationMetrics` (`models/tracked_post.py:22-24`) | ❌ | ❌ |
| engagement metrics (likes, impressions, rates) | `TrackedPostDocument` top-level (`models/tracked_post.py:41-49`) | ❌ | ❌ |
| full step trace | `PipelineRunDocument` (`models/pipeline_run.py`), keyed by `run_id` | ✅ (by `run_id`) | ❌ |

So we can see *what the soul was* when a post was made, and we can see *the full step trace of a run* — but **we cannot ask the one question the Interpreter exists to answer:** "which pipeline spec produced the highest-reward posts?" The post and the run are two ships passing in the night because `TrackedPostDocument` has no `run_id` and no `pipeline_hash`.

The fix is deliberately small and has two halves:

1. **The join (§3).** Add `run_id` + `pipeline_hash` to `PostCreationMetrics`, thread `run_id` from `run_account_pipeline` through `_run_account_pipeline` → `finalize_post` → `record_post`, and source `pipeline_hash` from the **walked pipeline spec's `version_hash`** (**CC-3**) — pre-06/07 via `PipelineSpecRepository().load_or_default(account_id, kind="post").version_hash` (doc 04), post-06/07 via `deps.live.pipeline_hash` threaded by doc 07 — at compose time, NOT off the account. This is the "ONE missing join field" the architecture review flagged. **This doc (02) owns adding both fields to `PostCreationMetrics`; the model edit (§3.1) MUST land before docs 06/07**, which stamp them in `publish_post`.

2. **The ledger (§4).** A new `OutcomeLedgerDocument` — `{run_id, account_id, post_id, soul_hash, pipeline_hash, reward, raw_metrics, recorded_at}` — written once at publish (with `reward=None`, metrics empty) and **updated in place** every time the engagement jobs refresh metrics. It is a **plain document projection**, not an event-sourced fold: one row per posted tweet, last-writer-wins, keyed by `outcomeledger/{account_id}-{post_id}`. This is the queryable surface a future self-rewrite / champion-challenger evaluator reads.

**Why a separate ledger doc at all, when `TrackedPostDocument` already holds metrics?** See §6 "Decision Defense → why a ledger instead of querying TrackedPost". Short version: the ledger is the *attribution-shaped* view (keyed and indexed for "group by pipeline_hash, average reward"), it carries the computed scalar `reward` that TrackedPost does not, and it decouples the evaluator from the polling schema so the metrics jobs stay untouched in shape.

---

## 2. File-by-file task index

### NEW

| File | Role (one line) |
|---|---|
| `backend/app/models/outcome_ledger.py` | `OutcomeLedgerDocument` (the attribution-join projection) + `compute_reward()` pure function. |
| `backend/app/services/outcome_ledger_repository.py` | `OutcomeLedgerRepository`: `stamp()` at publish, `update_outcome()` on metrics refresh, `list_for_pipeline_hash()` for the evaluator. |

### CHANGED

| File | Change (one line) |
|---|---|
| `backend/app/models/tracked_post.py` | Add `run_id: str \| None` + `pipeline_hash: str \| None` to `PostCreationMetrics` (lines 10-25). |
| `backend/app/interval/runner.py` **OR** `backend/app/pipeline/tools/data/publish_post.py` | Stamp `run_id` + `pipeline_hash` onto `creation_metrics`. **Pre-06/07:** edit `runner.py` (thread `run_id` into `_run_account_pipeline` at line 162; read `pipeline_hash` via `PipelineSpecRepository().load_or_default(account_id, kind="post").version_hash`; stamp both at the `PostCreationMetrics(...)` construction, lines 412-424). **Post-06/07:** that construction has moved into `publish_post.run` — stamp `live.run_id` + `live.pipeline_hash` there (the spec is loaded/walked once and threaded via deps, **CC-3/CC-7**; do not re-load the repo), doc 06 §5.2. See §3.2 (run_id), §3.3 (pipeline_hash source), §3.4 (both stamping homes). |
| `backend/app/interval/orchestration/post_tick.py` | After `record_post`, call `OutcomeLedgerRepository().stamp(...)` inside the existing `try` (lines 59-65). |
| `backend/app/jobs/engagement_job.py` | After `trepo.update_metrics(...)` (line 58), call `ledger.update_outcome(...)`. |
| `backend/app/jobs/early_engagement_job.py` | Same one-line ledger update after `update_metrics` (line 62). |

### REUSED (verbatim, no change)

| File | Why it is reused as-is |
|---|---|
| `backend/app/infrastructure/ravendb_http.py` | `put_document` / `get_document` / `query` (lines 103-152) — the ledger repo mirrors `PipelineRunRepository`'s use of these. No CAS needed (§6). |
| `backend/app/services/pipeline_run_repository.py` | The template the ledger repo copies almost line-for-line (`_safe_rql_string`, `_strip_meta`, `client` property, `put_document(..., collection=...)`). |
| `backend/app/metrics/derived.py` | `compute_rates` already runs in both jobs; `compute_reward()` consumes the same metric dict. We do NOT recompute rates. |
| `backend/app/models/tracked_post.py::PostCreationMetrics.voice_version_hash` | Already stamped (runner.py:420). The ledger's `soul_hash` reads this same value — no second source of truth. |

---

## 3. Slice A — the attribution join (`run_id` + `pipeline_hash`)

### 3.1 `PostCreationMetrics` — two new optional fields

**File:** `backend/app/models/tracked_post.py` (current model lines 10-25, verified).

```python
class PostCreationMetrics(BaseModel):
    """How a posted tweet was produced (optional on TrackedPosts)."""

    candidates_created: int = 0
    tweets_pulled: int = 0
    tweets_pulled_new: int = 0
    tweets_pulled_duplicates: int = 0
    regeneration_round: int = 0
    chosen_topic: str | None = None
    chosen_topic_id: str | None = None
    source_reference_tweet_id: str | None = None
    chosen_embed_url: str | None = None
    voice_version_hash: str | None = None
    voice_version_seq: int | None = None
    voice_version_label: str | None = None
    source_reference_metrics_at_pick: dict | None = None
    # ── NEW: attribution join (the ONE missing link) ──
    run_id: str | None = None          # joins this post to its PipelineRunDocument (pipelineruns/{run_id})
    pipeline_hash: str | None = None   # the active PipelineSpecDocument.version_hash at post time (doc 04)
```

Both default to `None`, so existing `TrackedPostDocument`s deserialize unchanged and `record_post`'s `model_dump(exclude_none=True)` (post_registry.py:148) simply omits them for legacy rows.

### 3.2 Thread `run_id` from the run wrapper into the pipeline body

**File:** `backend/app/interval/runner.py`.

`run_id` is created in `run_account_pipeline` (line 141: `run_id = ctx.forced_run_id or uuid4().hex`) but the inner `_run_account_pipeline(ctx, account)` (line 162) never receives it. Pass it through — it is already in scope at the only call site (line 153).

```python
# runner.py:139-159 (run_account_pipeline) — CHANGED call only
        try:
            out = _run_account_pipeline(ctx, account, run_id=run_id)   # CHANGED: pass run_id
            status = _run_status_from_out(out)
            return out

# runner.py:162 — CHANGED signature
def _run_account_pipeline(ctx: TickContext, account: AccountDocument, *, run_id: str) -> dict[str, Any]:
```

> **Why not read `ctx.forced_run_id`?** It is `None` for scheduled ticks (`interval/context.py:35`); the real id is the `uuid4().hex` computed in the wrapper. The wrapper is the only place that knows the canonical `run_id`, so it must pass it. Verified: `forced_run_id` is set only by the force-post path.

> **Post-06/07 note (no conflict):** once docs 06/07 land, `_run_account_pipeline` reads the canonical `run_id` from the dispatcher contextvar (`current_run_id()`, set by `run_events`; doc 07 §6) and sets it on the `TickRunContext` (`run_ctx.run_id`), then carries it to the ACT steps via `ActLive.run_id` (doc 06 §4.2). The explicit `run_id=` parameter above is the **pre-06/07** thread; doc 07's contextvar read supersedes it. Either way the same `run_id` reaches `publish_post`. Do NOT add both — apply the form matching the tree you are on.

### 3.3 The `pipeline_hash` source (read from the active spec, not the account)

`pipeline_hash` is the **walked spec's `version_hash`** (**CC-3**), read at post time from the live champion spec doc (doc 04 owns the model and the repo). There is **no** `account.pipeline_version_hash` accessor and none is added by any doc — the spec lives on a separate `pipelinespecs/{account_id}` document. **Pre-06/07** (the tree has no `ActLive`/deps yet), resolve it directly with one call via the single load API (**CC-5**):

```python
from app.services.pipeline_spec_repository import PipelineSpecRepository  # doc 04

_pipeline_hash = PipelineSpecRepository().load_or_default(account.account_id, kind="post").version_hash
```

**Post-06/07** this direct read goes away: doc 07 loads/walks the spec once at the top of the tick and threads its `version_hash` into `deps.live.pipeline_hash` (**CC-3, CC-7**); `publish_post` reads `live.pipeline_hash` and does **not** call the repo itself. For challenger slots the walked spec *is* the challenger, so `live.pipeline_hash` is the challenger's hash. See §3.4 for both stamping forms.

`load_or_default` (doc 04 §6b) returns the live **champion** spec, or the seeded baseline if no spec doc exists yet; `.version_hash` is `None` only on a brand-new baseline that has never been `save()`d (the bump stamps it on first write). A `None` `pipeline_hash` is a valid bucket ("baseline / unversioned"), so the join degrades gracefully — see §6.

> **Why read it here and not off the account?** The voice hash happens to live on the account (`account.voice_version_hash`) because the soul *is* embedded in the account doc; the pipeline spec is a **separate** document by design (doc 04 §3, §7 "separate challenger DOC"). Mirroring the voice accessor onto the account would force a second source of truth that has to be kept in sync with the spec doc on every promotion — exactly the drift doc 04 avoids. One read of the spec repo at compose time is the simpler, non-duplicating option.

### 3.4 Stamp both fields onto `creation_metrics`

The `creation_metrics` object is built once per post. **Where** you add the two lines depends on whether docs 06/07 have landed:

**Pre-06/07 (today's tree):** the construction is at `runner.py:412-424` (verified). Add `run_id` (the §3.2 parameter) and the `pipeline_hash` from §3.3:

```python
        _pipeline_hash = PipelineSpecRepository().load_or_default(account.account_id, kind="post").version_hash  # NEW (§3.3)
        creation_metrics = PostCreationMetrics(
            candidates_created=1,
            tweets_pulled=len(reference_pool),
            tweets_pulled_new=int(pull_stats.get("new_count") or 0),
            tweets_pulled_duplicates=int(pull_stats.get("duplicate_count") or 0),
            regeneration_round=selected_round if selected_round is not None else 0,
            source_reference_tweet_id=source_id,
            chosen_embed_url=topic_preanalysis.chosen_embed_url,
            voice_version_hash=account.voice_version_hash,
            voice_version_seq=account.voice_version_seq,
            voice_version_label=account.voice_version_label,
            source_reference_metrics_at_pick=source_metrics_at_pick,
            run_id=run_id,                    # NEW (§3.2 parameter)
            pipeline_hash=_pipeline_hash,     # NEW (§3.3 — active spec version_hash, doc 04)
        )
```

**Post-06/07 (after the ACT-path rewrite):** docs 06/07 delete `runner.py:412-424` and rebuild `creation_metrics` inside `publish_post.run` (doc 06 §5.2), which currently leaves a `# when 08 lands` placeholder for exactly these two fields. **This doc owns closing that placeholder.** In `app/pipeline/tools/data/publish_post.py`, the `PostCreationMetrics(...)` block reads `account = deps.live.account` and has both `live.run_id` and `live.pipeline_hash` in scope (the `ActLive` fields doc 06 §4.2 defines; doc 07 §6 populates `live.pipeline_hash` from the walked spec's `version_hash`, **CC-3, CC-7**). Stamp straight off `live` — do **not** re-load `PipelineSpecRepository` here (that would be a second source of truth and would read the *champion* even when a *challenger* spec was walked):

```python
    creation_metrics = PostCreationMetrics(
        # … existing fields built from `composed` and `account.voice_version_*` …
        source_reference_metrics_at_pick=composed.source_reference_metrics_at_pick,
        run_id=live.run_id,                  # NEW (doc 02) — ActLive field (CC-7)
        pipeline_hash=live.pipeline_hash,    # NEW (doc 02) — walked spec's version_hash, threaded via deps (CC-3, CC-7)
    )
```

> Use `live.run_id` and `live.pipeline_hash` (the `ActLive` fields doc 06 defines / doc 07 threads from the run wrapper and the walked spec). `live.run_id` equals `run_ctx.run_id == current_run_id()` (doc 07 §6) — trace, attribution, and the `publish_post` idempotency ledger key therefore all agree on one id. `live.pipeline_hash` is the hash of **the spec that was actually walked** (champion *or* challenger), which is why post-06/07 reads it from deps rather than re-loading the champion via the repo. Do not re-mint a `run_id` or re-load the spec here.

`account.voice_version_hash` is already read at the construction site in both forms — the new `pipeline_hash` line sits beside it. `pipeline_hash` is the §3.3 repo read (pre-06/07) or `live.pipeline_hash` (post-06/07); `run_id` is the §3.2 parameter (pre-06/07) or `live.run_id` (post-06/07).

No change is needed to `finalize_post` or `record_post` for the *join*: they already accept and persist `creation_metrics` verbatim (`post_tick.py:59-65`, `post_registry.py:130-149`). The join travels inside the existing object.

### 3.5 Definition of Done — Slice A

- `PostCreationMetrics` has `run_id` and `pipeline_hash`, both `str | None = None`.
- A scheduled post writes a `TrackedPostDocument` whose `creation_metrics.run_id` equals the `run_id` of the matching `pipelineruns/{run_id}` document, and whose `creation_metrics.pipeline_hash` equals the walked spec's `version_hash` — pre-06/07 `PipelineSpecRepository().load_or_default(account_id, kind="post").version_hash`, post-06/07 `live.pipeline_hash` (**CC-3**) — at post time (or `None` when the account has no saved spec yet — the baseline bucket).
- `python -m py_compile app/models/tracked_post.py app/interval/runner.py` clean (pre-06/07), or `app/pipeline/tools/data/publish_post.py` clean (post-06/07).
- Existing `TrackedPostDocument`s (no `creation_metrics` or no new fields) still load without error.

---

## 4. Slice B — the Outcome Ledger projection

### 4.1 `OutcomeLedgerDocument` + `compute_reward`

**File (NEW):** `backend/app/models/outcome_ledger.py`.

The document key is `outcomeledger/{account_id}-{post_id}` — **one row per posted tweet**, so a metrics refresh is an idempotent overwrite, never an append. This mirrors `TrackedPostDocument.document_id` (`{account_id}-{tweet_id}`), so the two are trivially co-locatable.

```python
"""Attribution-join projection: one row per posted tweet, linking a run + pipeline
version to the reward it ultimately earned. Plain last-writer-wins document — NOT
event-sourced. Stamped at publish, updated in place as engagement metrics arrive."""

from __future__ import annotations

from pydantic import BaseModel, Field


def compute_reward(metrics: dict | None) -> float | None:
    """Single scalar an evaluator optimizes. Engagement-rate first (impression-normalized,
    fairest across posts of different reach); falls back to None until impressions exist.

    `metrics` is the same dict the engagement jobs already build (it has been through
    compute_rates(), so engagement_rate/reply_rate/like_rate are present when impressions>0).
    We do NOT recompute rates here — we read what the job computed."""
    if not metrics:
        return None
    rate = metrics.get("engagement_rate")
    if isinstance(rate, (int, float)):
        return float(rate)
    return None


class OutcomeLedgerDocument(BaseModel):
    """One posted tweet's attribution row. Document id: outcomeledger/{account_id}-{post_id}."""

    run_id: str | None = None            # join → pipelineruns/{run_id} (may be None for legacy/force edge)
    account_id: str
    post_id: str                         # the X tweet id (== TrackedPostDocument.tweet_id)
    soul_hash: str | None = None         # account.voice_version_hash at post time
    pipeline_hash: str | None = None     # active PipelineSpecDocument.version_hash at post time (doc 04)
    reward: float | None = None          # compute_reward(raw_metrics); None until impressions land
    raw_metrics: dict = Field(default_factory=dict)  # last-seen engagement dict (snapshot, untruncated)
    recorded_at: str = ""                # ISO of the last write (publish, then each refresh)

    @staticmethod
    def document_id(account_id: str, post_id: str) -> str:
        return f"outcomeledger/{account_id}-{post_id}"
```

> **`soul_hash` vs `voice_version_hash` naming.** The ledger calls it `soul_hash` (the scope vocabulary), but the *value* is `account.voice_version_hash` — the field was not renamed in the soul refactor (see soul-pipeline `00-overview.md` "Deliberately deferred"). One value, two names at two layers; do not introduce a third.

### 4.2 `OutcomeLedgerRepository`

**File (NEW):** `backend/app/services/outcome_ledger_repository.py`. Copies the shape of `PipelineRunRepository` (verified: `_safe_rql_string`, `_strip_meta`, lazy `client` property, `put_document(doc_id, model_dump(exclude_none=True), collection=...)`).

```python
"""Persistence for the outcome ledger (RavenDB collection OutcomeLedger)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.infrastructure.ravendb_http import (
    RavenDBHttpClient,
    RavenDBHttpError,
    get_ravendb_client,
)
from app.models.outcome_ledger import OutcomeLedgerDocument, compute_reward

logger = logging.getLogger(__name__)

OUTCOME_LEDGER_COLLECTION = "OutcomeLedger"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_meta(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class OutcomeLedgerRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def stamp(
        self,
        *,
        account_id: str,
        post_id: str,
        run_id: str | None,
        soul_hash: str | None,
        pipeline_hash: str | None,
    ) -> None:
        """Create the ledger row at publish time. reward stays None / raw_metrics empty
        until the engagement jobs fill them. Idempotent: re-stamping the same post just
        overwrites the (still empty) header — it does NOT clobber metrics, because at
        publish there are none yet. (A real re-publish is prevented upstream by post locks.)"""
        doc = OutcomeLedgerDocument(
            account_id=account_id,
            post_id=post_id,
            run_id=run_id,
            soul_hash=soul_hash,
            pipeline_hash=pipeline_hash,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        doc_id = OutcomeLedgerDocument.document_id(account_id, post_id)
        self.client.put_document(
            doc_id, doc.model_dump(exclude_none=True), collection=OUTCOME_LEDGER_COLLECTION
        )

    def update_outcome(self, account_id: str, post_id: str, metrics: dict) -> None:
        """Refresh reward + raw_metrics from the latest poll. Last-writer-wins.
        No-op if the row was never stamped (a post made before this feature shipped):
        we do NOT fabricate attribution we never captured."""
        doc_id = OutcomeLedgerDocument.document_id(account_id, post_id)
        raw = self.client.get_document(doc_id)
        if raw is None:
            return  # never stamped → no attribution header to attach metrics to; skip silently
        try:
            base = OutcomeLedgerDocument.model_validate(_strip_meta(raw))
        except Exception as exc:
            logger.debug("OutcomeLedger invalid row %s: %s", doc_id, exc)
            return
        base.raw_metrics = dict(metrics)
        base.reward = compute_reward(metrics)
        base.recorded_at = datetime.now(timezone.utc).isoformat()
        self.client.put_document(
            doc_id, base.model_dump(exclude_none=True), collection=OUTCOME_LEDGER_COLLECTION
        )

    def list_for_pipeline_hash(
        self, pipeline_hash: str, *, account_id: str | None = None, limit: int = 500
    ) -> list[OutcomeLedgerDocument]:
        """The evaluator's read path: every scored outcome for a given pipeline version."""
        ph = _safe_rql_string(pipeline_hash)
        if not ph:
            return []
        clauses = [f'pipeline_hash == "{ph}"']
        if account_id:
            aid = _safe_rql_string(account_id)
            if aid:
                clauses.append(f'account_id == "{aid}"')
        cap = max(1, min(int(limit), 500))
        rql = (
            f"from {OUTCOME_LEDGER_COLLECTION} where "
            + " and ".join(clauses)
            + f" order by recorded_at desc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("OutcomeLedger query failed: %s", exc)
            return []
        out: list[OutcomeLedgerDocument] = []
        for raw in rows:
            try:
                out.append(OutcomeLedgerDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("OutcomeLedger skip invalid row: %s", exc)
        return out
```

### 4.3 Stamp the ledger at publish

**File:** `backend/app/interval/orchestration/post_tick.py`, inside `finalize_post`, in the existing `if ctx.post_registry:` block right after `record_post` (current lines 57-65, verified).

```python
    if ctx.post_registry:
        try:
            ctx.post_registry.record_post(
                account.account_id,
                account.last_post_id,
                ctx.now_iso,
                creation_metrics=creation_metrics,
                followers_at_post=followers_at_post,
            )
            # ── NEW: open the attribution row for this post (reward filled later by jobs) ──
            OutcomeLedgerRepository().stamp(
                account_id=account.account_id,
                post_id=account.last_post_id,
                run_id=creation_metrics.run_id if creation_metrics else None,
                soul_hash=creation_metrics.voice_version_hash if creation_metrics else None,
                pipeline_hash=creation_metrics.pipeline_hash if creation_metrics else None,
            )
            m = ctx.twitter.get_tweet_metrics(account.account_id, account.last_post_id)
            # … unchanged …
```

Add the import at the top of `post_tick.py`:
```python
from app.services.outcome_ledger_repository import OutcomeLedgerRepository
```

The stamp lives **inside the existing `try`** that already guards `record_post` (post_tick.py:58-73): a ledger write failure must never break publishing — the post is already live on X. It is the same fault-tolerance contract `record_post` already has (its exception is caught and logged at line 72-73).

> **Stable across the 06/07 rewrite.** This edit is in `finalize_post`, which docs 06/07 call **unchanged** from inside `publish_post` (doc 06 §5.2 reuses `finalize_post` verbatim). The stamp reads its three values off the frozen `creation_metrics` object, not off `account`, so it needs **no** relocation when the ACT path is rewritten — it works identically pre- and post-06/07.

> **Why read from `creation_metrics` rather than `account.*` here?** `creation_metrics` is the single object that was *frozen at compose time*; reading `soul_hash`/`pipeline_hash`/`run_id` off it guarantees the ledger header and the `TrackedPostDocument` agree exactly, even if `account` were mutated between compose and finalize. It also means `finalize_post` needs no new parameters.

### 4.4 Fill the ledger as metrics arrive

The two engagement jobs are the **only** writers of post metrics (verified: `engagement_job.py:58` and `early_engagement_job.py:62` both call `trepo.update_metrics(aid, tid, m)`, and nothing else does). Add one ledger call immediately after each, reusing the `m` dict that already has rates merged in.

> **Naming foot-gun — `ledger` is NOT `outcomes`.** Both jobs already construct `outcomes = PipelineOutcomeRepository()` (a pre-existing, *different* repo — `services/pipeline_outcome_repository.py`, `engagement_job.py:23` / `early_engagement_job.py:23`) for per-phase run telemetry. This doc adds a second, near-identically-named `ledger = OutcomeLedgerRepository()` (the attribution-join projection in the `OutcomeLedger` collection). They are distinct classes writing distinct collections — do **not** call `outcomes.append(...)` where you mean `ledger.update_outcome(...)`, or vice versa. Name the new local `ledger` (never `outcomes`) to keep the two visually separate at the call site.

**File:** `backend/app/jobs/engagement_job.py` (after line 58, `trepo.update_metrics(aid, tid, m)`):
```python
                trepo.update_metrics(aid, tid, m)
                ledger.update_outcome(aid, tid, m)   # NEW
```
Construct `ledger` once near the other repos at the top of `run_engagement_job` (alongside `trepo`, line 20):
```python
    ledger = OutcomeLedgerRepository()
```
and import it:
```python
from app.services.outcome_ledger_repository import OutcomeLedgerRepository
```

**File:** `backend/app/jobs/early_engagement_job.py` — identical: construct `ledger = OutcomeLedgerRepository()` near line 20, import the repo, and add `ledger.update_outcome(acc.account_id, tid, m)` right after `trepo.update_metrics(acc.account_id, tid, m)` (line 62). The `m` dict here has already been through `compute_rates` + velocity (early_engagement_job.py:51-61), so `compute_reward` sees the same `engagement_rate` the snapshot stores.

> **Why not a single shared helper?** The two jobs already duplicate the `update_metrics` + snapshot-save shape (compare engagement_job.py:54-79 and early_engagement_job.py:47-79); a one-line `ledger.update_outcome(...)` next to the existing duplicated `update_metrics` matches the house pattern. Extracting a helper for two call sites is the speculative abstraction CLAUDE.md warns against.

### 4.5 Definition of Done — Slice B

- `outcomeledger/{account_id}-{post_id}` exists immediately after a successful post, with `run_id`/`soul_hash`/`pipeline_hash` populated and `reward=None`, `raw_metrics={}`.
- After the next `engagement_job` (or `early_engagement_job`) run that polls that tweet, the same document has `reward` = its `engagement_rate` (or `None` if impressions are still 0) and `raw_metrics` populated, with a newer `recorded_at`.
- `OutcomeLedgerRepository().list_for_pipeline_hash(h)` returns the rows for pipeline version `h`, newest first — the evaluator's read path.
- `update_outcome` on a post that was never stamped (pre-feature tweet) is a silent no-op (no exception, no fabricated row).
- `python -m py_compile` clean across the two new files and the four changed files.

---

## 5. Implementation order

`3.1 (model field) → 4.1 (ledger model + reward) → 4.2 (repository) → 3.2/3.3/3.4 (thread run_id + read pipeline_hash + stamp creation_metrics) → 4.3 (stamp at publish) → 4.4 (jobs fill it)`.

Rationale: the two model changes have no dependencies and unblock everything; the repository needs the model; the runner/`publish_post` changes need the new `PostCreationMetrics` fields; the publish stamp needs the repository; the jobs come last. Slice A (the join) is independently shippable and valuable even if Slice B (the ledger) slips. **Cross-slice gate:** §3.1's model edit must merge before docs 06/07 (they construct `PostCreationMetrics` and would crash on the missing fields); the `pipeline_hash` read (§3.3) only needs doc 04's `PipelineSpecRepository`/`load_or_default` to exist — until then `version_hash` is `None` and the join still works in the baseline bucket.

---

## 6. Decision Defense

**Why a plain document projection, not event-sourcing?**
The scope phrase is "Plain document projection — NO event-sourcing needed," and the data shape proves it: there is exactly **one** post per tweet id, and metrics polling is **idempotent overwrite** (the engagement job already does last-writer-wins on `TrackedPostDocument` via `update_metrics` → `put_document`). There is no history to fold and no concurrent-writer contention (the two jobs poll disjoint windows and, even overlapping, both write the same converged metric snapshot). An event log + projection consumer (as exists for `PipelineRunDocument`) would add a NATS dependency and a replay story for zero benefit. The ledger is a *cache of the answer*, recomputed every poll.

**Why a ledger instead of just querying `TrackedPostDocument`?**
Three reasons, all concrete: (1) `TrackedPostDocument` has no `reward` scalar — the evaluator would have to recompute it on every read, and the reward definition would live in query code instead of one pure function. (2) The join keys (`pipeline_hash`, `run_id`) live *nested* inside `creation_metrics` on TrackedPost, which RavenDB cannot index/group as cheaply as top-level fields; the ledger lifts them to the top level for `where pipeline_hash == ...`. (3) It decouples the evaluator (doc on self-rewrite) from the polling schema — the metrics jobs keep their exact current shape; we only *append* one call. If we later change reward, we touch one function, not the jobs.

**Why no RavenDB CAS / If-Match on `update_outcome`?**
The grounding confirms the HTTP client has no CAS (`ravendb_http.py:103-110`, unconditional PUT) and the architecture explicitly does not need it. The only writers are the two engagement jobs; a race between them produces the *same* converged metrics (both read X, both compute the same `engagement_rate`), so last-writer-wins is correct, not lossy. This is identical to how `TrackedPostRepository.update_metrics` already operates with no CAS.

**pipeline_hash source of truth (and the graceful default).**
`pipeline_hash` is the digest of the active `PipelineSpecDocument` — its `version_hash` field, computed by `compute_pipeline_hash` (doc 04 §5a). Doc 04 deliberately keeps the spec, and therefore its hash, on a **separate** `pipelinespecs/{account_id}` document, **not** on the account: the soul is embedded in the account doc (hence `account.voice_version_hash`), but the spec is its own versioned, champion/challenger document (doc 04 §3, §7). So this task does **not** read an `account.pipeline_version_hash` accessor — none exists, and adding one would create a second source of truth that has to be re-synced on every promotion (the exact drift doc 04's separate-doc design avoids).

**Pre-06/07**, read it once at compose time via the single load API (**CC-5**):
```python
PipelineSpecRepository().load_or_default(account.account_id, kind="post").version_hash
```
**Post-06/07**, do **not** read the repo inside `publish_post`: doc 07 loads/walks the spec once and threads its `version_hash` into `deps.live.pipeline_hash` (**CC-3, CC-7**); `publish_post` stamps `live.pipeline_hash`. This is the only correct source for a challenger slot, where the walked spec is the challenger, not the champion — a repo re-load would read the champion and mis-attribute the post. `load_or_default` (doc 04 §6b) returns the live **champion** spec, or the seeded baseline if no spec doc exists. **If doc 04's seed has not been run** for this account, `load_or_default` still returns a baseline `PipelineSpecDocument` whose `version_hash` is `None` until first `save()` — and `pipeline_hash=None` is a valid bucket (groups as "baseline / unversioned"). Do **not** compute a hash here; computing it is doc 04's job (`compute_pipeline_hash`), and a second computation would drift. The join degrades gracefully: a `None` pipeline_hash still groups correctly.

**Sequencing relative to docs 06/07.** Docs 06/07 move the `creation_metrics` construction out of `runner.py:412-424` and into `publish_post.run`, where doc 06 §5.2 left a `# when 08 lands` placeholder for `run_id`/`pipeline_hash`. **This doc (02) owns that placeholder** (the cross-doc note in doc 06 mis-numbers it "doc 08"; the attribution field-add and its stamping are doc 02). §3.1's model edit must therefore merge **before** 06/07 land — otherwise `PostCreationMetrics(run_id=...)` raises an extra-field error — and the stamping lines in §3.4 land in `publish_post.run` once 06/07 are in.

**Why `reward = engagement_rate` and not a composite score?**
Engagement rate is impression-normalized, so it compares fairly across posts of wildly different reach — the right default optimization target. It is already computed by `compute_rates` (`metrics/derived.py:17-36`) and stored on both `TrackedPostDocument` and `PostMetricSnapshotDocument`, so the ledger's `reward` is consistent with everything else by construction. `compute_reward` is isolated as one pure function precisely so a future doc can swap in a follower-delta-weighted reward without touching the jobs, the repo, or the model. Returning `None` until impressions exist (rather than `0.0`) keeps "not yet measured" distinct from "measured zero" — the evaluator must not treat a fresh post as a failure.

**Why stamp at publish with empty metrics instead of waiting for the first poll?**
The attribution header (`run_id`, `pipeline_hash`, `soul_hash`) is only knowable at publish — by the time the engagement job runs, it has the tweet id but not the run context. Stamping at publish captures the join while we hold it; the job later attaches metrics by key. This also makes `update_outcome` a clean no-op for pre-feature posts (no header → nothing to update), which is exactly the graceful-degradation behavior we want for the lone existing account's history.

**Why does `update_outcome` skip (not create) when the row is missing?**
A missing row means the post predates this feature (or the publish stamp failed and the post is already live). Creating a row there would have a `run_id`/`pipeline_hash` we never captured — fabricated attribution. Skipping keeps the ledger honest: it only contains posts whose provenance we actually recorded. Same principle as the revision archive in soul-pipeline `02` ("filling a missing field would FABRICATE history").

---

## 7. Verification (manual, single account)

1. **Join present:** Force-post `JohnJames_News`. `GET` the new `trackedposts/JohnJames_News-{tweet_id}` and confirm `creation_metrics.run_id` matches the run's `pipelineruns/{run_id}` and `creation_metrics.pipeline_hash` equals the walked spec's `version_hash` — `PipelineSpecRepository().load_or_default("JohnJames_News", kind="post").version_hash` (the `version_hash` on `pipelinespecs/JohnJames_News`, or `None` if no spec has been seeded yet). Post-06/07 this equals `live.pipeline_hash` (**CC-3**).
2. **Ledger stamped:** Confirm `outcomeledger/JohnJames_News-{tweet_id}` exists with `reward: null`, `raw_metrics: {}`, and the three hashes/ids populated.
3. **Ledger filled:** Run `run_engagement_job()` (or wait for the scheduled tick) after the post has impressions; re-GET the ledger row and confirm `reward` is a float == the TrackedPost's `engagement_rate` and `recorded_at` advanced.
4. **No-op safety:** Run the job against a tweet with no stamped ledger row (e.g., a historical post) and confirm no `OutcomeLedger` document is created for it.
5. **Compile/health:** `python -m py_compile` on all six touched files; `docker compose up -d --build` healthy; existing pytest green (no test asserts on `PostCreationMetrics` field count — additive `None` fields are safe).

# 06 — The ACT Path as Typed Steps (the crux)

> **Status:** Ready to implement. Authored cold against the live tree on branch `feat/platform-overhaul`; verified every API/field/signature against the actual files (paths + line numbers below are real as of authoring).
> **Scope:** Backend only. Two new catalog tools (`compose_until_safe`, `publish_post`), three new `ArtifactKey`s + Pydantic models, a one-field extension of `PostRunDeps` (`live: ActLive`), the two ACT `Step`s appended to the runbook, and their `services/steps.py` wrappers — so the *whole* pipeline (SENSE steps + compose + publish) is data at a meaningful grain. **The rewrite of `interval/runner.py::_run_account_pipeline` into a single `run_steps` walk, and the deletion of `reference_phase.py`, are `07`'s slice** (see the ownership boundary below); this doc supplies the tools/artifacts/`ActLive` that `07`'s new runner consumes.
> **The hard part of the whole plan lives here.** The typed engine today runs ONLY the SENSE/reference phase. The compose → guardian → regenerate → select → publish tail is hand-written imperative code on a *different* context object. This doc turns that tail into two coarse typed steps without changing behavior.

**Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB, APScheduler in-process threadpool, synchronous tick — NOT async).

**Ownership boundary with `07` (read this first — it resolves the one cross-doc overlap):**
`13-verification-and-sequencing.md` §2 sequences `06 → 07` as one atomic import-break unit and assigns the two halves cleanly: **this doc (`06`) owns the two new catalog tools, the three new `ArtifactKey`s + models, and the `PostRunDeps.live` / `ActLive` extension.** **`07` owns the runner rewrite** (`_run_account_pipeline` becomes ONE `run_steps` walk of the compiled spec), the deletion of `interval/reference_phase.py`, the `run_steps` `wrappers` param + `engine_invariants`, the `CostMeter`, and `_result_from_run` (the function that maps the terminal artifacts back to the legacy return dict). Where this doc previously sketched its own imperative runner drive, that sketch is superseded by `07` and is **not** the target code — see §7, which now records only what `06` contributes to the runner. There is exactly ONE runner shape (07's single-`run_steps`-walk) and exactly ONE `PostRunDeps` extension (this doc's `live: ActLive`).

**Cross-references (sibling docs in this folder — by their real filenames):**
- **`04-pipeline-spec-and-versioning.md`** — owns the `PipelineSpecDocument` shape and `PipelineSpecRepository.load_or_default(account_id).version_hash`, which is the **`pipeline_hash`** this doc stamps onto the published post (§5.2). `pipeline_hash` does NOT live on the account; it is the loaded champion spec's `version_hash`, threaded into `ActLive.pipeline_hash` by `07`'s runner.
- **`05-validator-and-compiler.md`** — its validator R6/R7 hard-code `ArtifactKey.PUBLISHED_POST` and require a terminal publish leaf plus a step that writes `SAFETY_VERDICT`. **There is NO `invariant_tool`/`TOOL_INVARIANT` flag** (canonical contract **CC-2**): doc 05 detects the required structure purely from each tool's declared **catalog `writes`** — the guardian-bearing tool is "the catalog tool whose `writes` includes `SAFETY_VERDICT`" (= `compose_until_safe`) and the publish tool is "the catalog tool whose `writes` includes `PUBLISHED_POST`" (= `publish_post`). This doc's job is therefore only to make both tools declare those static `TOOL_WRITES` (§5) so R6/R7 grade them — it does NOT add or set any invariant flag. The catalog's `compose` `reads` tuple must match §7.1.
- **`07-interpreter-wiring.md`** — owns the runner rewrite, the engine `wrappers`, the `CostMeter`, and `_result_from_run`. This doc treats the guardian *inside* `compose_until_safe` as the compose-loop's reject-feedback driver, which is **distinct** from `07`'s engine-level non-bypassable guardian/cost wrappers (see §6 Decision Defense).
- **`08-step-trace-full-fidelity.md`** — owns `StepOutputDocument` (full-fidelity per-step trace) and the in-process capture sink. This doc only guarantees the new steps emit/capture the same artifacts every other step does; it does NOT define the trace docs. `08`'s step-boundary hook captures `compose_until_safe`/`publish_post` automatically because they flow through the same `_run_step_with_progress` engine path.
- **`02-outcome-ledger-attribution.md`** — owns adding `run_id` + `pipeline_hash` to `PostCreationMetrics`. This doc's `publish_post` stamps both onto `creation_metrics`, but the model-field addition is `02`'s slice. **Hard sequencing: `02`'s field add MUST be merged before this doc's `publish_post` can set `run_id=`/`pipeline_hash=` (constructing `PostCreationMetrics(run_id=...)` against today's model would raise an extra-field error).** See §5.2.

---

## 1. Why this is the crux

The grounding is blunt about it and the live code confirms it:

| Phase | Where it runs today | Context object | Typed? |
|---|---|---|---|
| SENSE (profile → pools → rank → brief) | `interval/reference_phase.py:70-155` → `run_steps(POST_TICK_REFERENCE_STEPS, …)` | `TickRunContext` (serializable) | ✅ typed steps |
| DECIDE→ACT (compose → guardian → regen → select → publish) | `interval/runner.py:304-441` (hand-written; loop body `304-365`, `creation_metrics` `412-424`, `finalize_post` `426-435`) | `TickContext` (live services) | ❌ imperative |

So "make the pipeline data" is **not** done by the SENSE engine alone. The editable spec stops at the last brief and the real decision/action is opaque imperative code. To make the pipeline genuinely data-as-spec at a *meaningful* grain we must give the ACT tail a `Step`/`ArtifactKey` representation that the same generic interpreter walks.

**The compose loop is irreducibly imperative** (verified at `interval/runner.py:304-365` — outer loop at `304`, inner regeneration loop at `321`): an outer loop over ranked references (fallback) wrapping an inner loop over regeneration rounds (guardian reject-reason fed back into the next compose). We do **not** flatten this into steps. We wrap the entire loop in ONE coarse catalog tool, `compose_until_safe`, that owns the loop internally — **including building the `ranked_refs` fallback list from the `TIMELINE_RANKED` artifact** (the work `reference_phase.ranked_refs_from_runbook` does today; `07` deletes `reference_phase.py` and moves that helper here, §5.1). Publishing becomes a second coarse tool, `publish_post`. The graph stays data at the grain that matters: `…SENSE steps… → compose_until_safe → publish_post`.

---

## 2. File-by-file change index

### NEW

| File | Role (one line) |
|---|---|
| `app/pipeline/tools/llm/compose_until_safe.py` | Coarse LLM tool: owns the ref-fallback × regeneration loop; writes `COMPOSED_POST` + `SAFETY_VERDICT`. |
| `app/pipeline/tools/data/publish_post.py` | Coarse data tool: wraps `finalize_post` with an idempotency marker; writes `PUBLISHED_POST`. |

### CHANGED

| File | Change |
|---|---|
| `app/pipeline/types/artifacts.py` | Add 3 `ArtifactKey`s (`COMPOSED_POST`, `SAFETY_VERDICT`, `PUBLISHED_POST`) + 3 Pydantic models + 3 `ARTIFACTS` entries. |
| `app/pipeline/services/deps.py` | Extend `PostRunDeps` with exactly ONE new field — `live: ActLive | None = None` — the side-channel carrying every ACT-only handle (live `guardian`, `max_regeneration_rounds`, `bypass_post_cooldown`, the `AccountDocument`, the `TickContext`, `run_id`, `pipeline_hash`, `copied_exclude`, etc.). Also define the `ActLive` dataclass here (§4.2). |
| `app/pipeline/services/steps.py` | Add two thin wrappers `compose_step` / `publish_step` that forward `(ctx, deps)` to the new tools (§7.2). |
| `app/pipeline/runbooks/post_tick.py` | Append the two ACT `Step`s after `summarize_for_compose` (§7.1). |
| `app/pipeline/runbooks/post_tick.py` (frontend-sync header) + `frontend/src/lib/pipeline/flowGraph.ts` | Add `compose_until_safe` + `publish_post` nodes (top-level → bare dotted ids), replacing the ad-hoc `compose`/`safety`/`publish`/`complete` orchestrator nodes (§7.1). |
| `tests/test_orchestrator.py`, `tests/unit/test_pipeline_runbook.py` | Update the patch target + the hard-coded step-id lists that this doc's runbook append breaks (§7.5). |

### REUSED (verbatim, no edits)

| File | What we reuse |
|---|---|
| `app/interval/compose_timeline_post.py:269-280` | `compose_formatted_post(...)` (signature `269-280`, body to `347`) — called unchanged from inside `compose_until_safe`. |
| `app/agents/safety_guardian.py:22-34, 90-91` | `guardian.evaluate()` (`22-34`) + `is_niche_mismatch_reject()` (`90-91`) — called unchanged inside the loop. |
| `app/interval/orchestration/post_tick.py:23-96` | `finalize_post(...)` — called unchanged from inside `publish_post`. Returns `{account_id, tweet: <full tw_result>, regeneration_round, note?, creation_metrics?}` (`86-96`). |
| `app/interval/tweet_topic_preanalysis.py:22, 112` | `GatheredTweet` (`22`, for `model_validate` of ranked rows) / `preanalysis_from_winner` (`112`) — called inside `compose_until_safe`. (`apply_preanalysis_to_account_bundle`, `179`, is trace-only and stays in the runner if the bundle SSE trace is kept — see §5.1.) |
| `app/interval/reference_context.py:35` + `app/services/tick_data_service.py:199` + `app/social/tweet_enrichment.py:300` | `format_reference_context_for_compose(...)` / `TickDataService.merge_reference_pool(...)` (`@staticmethod`) / `filter_rows_with_urls(...)` — called inside `compose_until_safe._reference_inputs` to derive the compose-context block + reference pool from the SENSE artifacts (CC-7; replaces the old `ActLive` reference fields). |
| `app/pipeline/_runbook_engine.py` | `run_steps` (`151`) / `_run_step_with_progress` (`42`) — the generic interpreter. **`07` adds the `wrappers` param**; this doc adds nothing here. |
| `app/pipeline/types/context.py` | `set_artifact` (`45-52`) / `get_artifact` (`30-37`) — the serializable artifact channel. Note `set_artifact` stores `model_dump(mode="json")` and `get_artifact` re-validates the stored dict back to a model instance. |

> **Not edited here (owned by `07`):** `app/interval/runner.py::_run_account_pipeline` (the runner rewrite to a single `run_steps` walk), `app/interval/reference_phase.py` (DELETED by `07`; its `post_run_deps_from_tick` and `ranked_refs_from_runbook` move — the latter INTO `compose_until_safe`, see §5.1), and the `run_steps` `wrappers`/`CostMeter` plumbing. This doc only defines the tools/artifacts/`ActLive` that `07`'s new runner body consumes. See §7 for the precise hand-off.

---

## 3. The three new artifacts (`app/pipeline/types/artifacts.py`)

These are the serializable *views* that flow through `ctx.data` and get traced. The non-serializable live objects (the `GatheredTweet` winner, the `AccountDocument`) travel via `deps.live` (§4.2), never through `model_dump`.

### 3.1 `ArtifactKey` additions (after line 24)

```python
class ArtifactKey(StrEnum):
    ACCOUNT_BUNDLE = "account_bundle"
    TIMELINE_REFERENCES = "timeline_references"
    SEARCH_REFERENCES = "search_references"
    OWN_POSTS = "own_posts"
    TIMELINE_RANKED = "timeline_ranked"
    OWN_POSTS_RANKED = "own_posts_ranked"
    TIMELINE_ANALYSIS = "timeline_analysis"
    OWN_POSTS_ANALYSIS = "own_posts_analysis"
    # ── ACT phase (new) ───────────────────────────────────────────────
    COMPOSED_POST = "composed_post"
    SAFETY_VERDICT = "safety_verdict"
    PUBLISHED_POST = "published_post"
```

### 3.2 Models (add near the other artifact models, before `ArtifactDef`)

```python
class ComposedPost(BaseModel):
    """The selected post body and the provenance of the compose loop that produced it.

    This is the SERIALIZABLE view. The live winner GatheredTweet and the resolved
    chosen_embed_url object travel via deps.live (not here) so we never force a
    non-serializable through model_dump.
    """

    model_config = ConfigDict(extra="allow")

    body: str
    # Outer-loop bookkeeping (mirrors runner.py:304-365 today)
    reference_index: int = 0          # which ranked ref won (0-based)
    references_tried: int = 0
    regeneration_round: int = 0       # inner-loop round of the accepted body
    source_reference_tweet_id: str | None = None
    chosen_embed_url: str | None = None
    # Source-pick metrics snapshot (mirrors runner.py:402-411)
    source_reference_metrics_at_pick: dict[str, Any] | None = None
    # Compose-cost bookkeeping for the creation metrics
    tweets_pulled: int = 0
    tweets_pulled_new: int = 0
    tweets_pulled_duplicates: int = 0


class SafetyVerdict(BaseModel):
    """Final guardian outcome of the compose loop.

    approved=True  → a body passed guardian.evaluate(); compose_until_safe wrote COMPOSED_POST.
    approved=False → every reference/round was rejected; last_reject is the terminal reason
                     and COMPOSED_POST is absent. publish_post will skip.
    """

    approved: bool
    last_reject: str | None = None
    references_tried: int = 0          # the rejected legacy return needs this (runner.py:373)
    regeneration_round: int = 0        # round of the accepted body (0 when rejected)


class PublishedPost(BaseModel):
    """Result of the X publish + finalize. Carries the FULL finalize_post() dict under
    `result` so the runner can reconstruct the exact legacy return shape (including the
    full `tweet` object), plus flat convenience fields for the trace/dashboard."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    posted: bool = False
    tweet_id: str | None = None
    skipped_reason: str | None = None          # set when SAFETY_VERDICT.approved is False
    regeneration_round: int | None = None
    idempotency_key: str | None = None          # see §5.2
    note: str | None = None
    # The COMPLETE finalize_post(...) return dict ({account_id, tweet, regeneration_round,
    # note?, creation_metrics?}) — verbatim, untruncated. The runner's _result_from_run (07)
    # returns THIS as the legacy result so `'tweet' in out` and the full tweet object survive.
    result: dict[str, Any] = Field(default_factory=dict)
```

> **Why `PUBLISHED_POST` with a `result` dict — canonical per CC-4.** Canonical contract **CC-4** is authoritative: the terminal artifact is `ArtifactKey.PUBLISHED_POST` carrying a `PublishedPost` model with a **`.result`** field; **`PUBLISH_RESULT` does not exist** (no such `ArtifactKey`, no such model). Doc `05`'s validator R6/R7 also key on `PUBLISHED_POST`, so the key is locked. The `.result` dict carries the FULL `finalize_post(...)` return verbatim, so the runner can reconstruct the exact legacy shape: the live tests assert `'tweet' in out` (`tests/test_orchestrator.py:109,165`, verified — `'tweet'` comes from `finalize_post`'s return at `post_tick.py:88`), and `'tweet' in published.result` holds because `result` is that whole dict. **This doc owns the canonical `PublishedPost` model (with `.result`).** `07`'s `_result_from_run` reads `run_ctx.get_artifact(ArtifactKey.PUBLISHED_POST).result` and returns it verbatim. (If a draft of `07` flattened `PublishedPost` and dropped `.result`, that draft diverges from CC-4 and must be re-pointed to read `.result` — CC-4 wins.)

### 3.3 `ARTIFACTS` registrations (append to the dict, after `OWN_POSTS_ANALYSIS`)

```python
    ArtifactKey.COMPOSED_POST: ArtifactDef(
        ArtifactKey.COMPOSED_POST,
        ComposedPost,
        "Selected post body + compose-loop provenance",
        "steps.compose_step",
    ),
    ArtifactKey.SAFETY_VERDICT: ArtifactDef(
        ArtifactKey.SAFETY_VERDICT,
        SafetyVerdict,
        "Final guardian verdict of the compose loop",
        "steps.compose_step",
    ),
    ArtifactKey.PUBLISHED_POST: ArtifactDef(
        ArtifactKey.PUBLISHED_POST,
        PublishedPost,
        "X publish + finalize result",
        "steps.publish_step",
    ),
```

> **Note (verified):** `ARTIFACTS` is a module-level dict and `set_artifact` validates against `ARTIFACTS[key].model` (`context.py:45-52`). Both new tools MUST write via `ctx.set_artifact(...)`; raw `ctx.set("composed_post", …)` would bypass validation and break `get_artifact`.

### Definition of Done — §3
- `python -m py_compile app/pipeline/types/artifacts.py` clean.
- `ARTIFACTS` has 11 entries; `len(ArtifactKey) == 11`.
- `ctx.set_artifact(ArtifactKey.COMPOSED_POST, {"body": "x"})` round-trips via `get_artifact`.

---

## 4. Reconciling the two contexts (the central design decision)

Today's ACT path runs on `TickContext` (`interval/context.py:20-32`) which carries the live services and mutable config the loop needs: `repo`, `twitter`, `guardian`, `tick_data`, `post_registry`, `max_regeneration_rounds` (`context.py:31`), `bypass_post_cooldown` (`context.py:32`), plus the per-account lock dicts. The typed engine runs on `TickRunContext` (`types/context.py:15-56`) whose only payload is a serializable `data` dict.

For the ACT steps to run under the *same* interpreter, the things the loop needs must reach the tool's `run()`. Tools receive exactly two arguments: `(ctx: TickRunContext, deps: PostRunDeps)` (`flow.py`, `_runbook_engine.py:65`). So **everything the loop needs that is not already in `ctx.data` must arrive via `deps`.** That is the reconciliation.

### 4.1 Extend `PostRunDeps` with exactly ONE field — `live: ActLive` (`app/pipeline/services/deps.py`)

`PostRunDeps` already carries `tick_data`, `repo`, `post_registry`, `pulled_tweets`, `twitter` (verified, `deps.py:14-22`). Rather than scatter the ACT handles across several new top-level fields, we add **one** field — a `live: ActLive` side-channel that owns *every* ACT-only input (the live `guardian`, `max_regeneration_rounds`, `bypass_post_cooldown`, the `AccountDocument`, the `TickContext`, `run_id`, `pipeline_hash`, `copied_exclude`, …). This is the shape `13-verification-and-sequencing.md` §2 names ("06 adds `PostRunDeps.live`"), and it keeps the injected-vs-proposable split honest: **nothing on `PostRunDeps` is LLM-tunable; only the spec's per-step config is.**

```python
@dataclass
class PostRunDeps:
    tick_data: TickDataService
    repo: AccountRepository
    post_registry: TrackedPostRepository | None = None
    pulled_tweets: PulledTweetRepository | None = None
    twitter: TwitterService | None = None
    # ── ACT-phase side-channel (engine-injected; never proposable in a spec) ──
    live: ActLive | None = None                # non-serializable handles, see §4.2
```

> **Why one `live` field, not several (`guardian`/`account`/`tick_ctx`/… directly)?** A single side-channel keeps the deps contract a single edit, keeps the SENSE-only call sites and `PostRunDeps.build()` untouched, and gives `08`/the trace one obvious thing to *not* serialize (the whole `live` object is non-serializable by construction). `07`'s runner populates `deps.live = ActLive(...)` once, after the SENSE artifacts exist (§4.3). **Reconciliation with `07` §2.5:** `07` previously added `account` + `tick_ctx` directly on `PostRunDeps`; those move onto `ActLive` (`live.account`, `live.tick_ctx`) so there is ONE deps extension. `07`'s runner sets `deps.live`, not `deps.account`/`deps.tick_ctx`.

`PostRunDeps.build()` (the standalone constructor at `deps.py:24-44`) is used by tests and tools that don't have a `TickContext`. Leave its body as-is; the new field defaults to `None`, so `build()` callers that never run the ACT steps are unaffected.

### 4.2 The `live` side-channel — passing non-serializable objects WITHOUT `model_dump`

The compose loop needs live objects and config that must NOT go through `set_artifact` (which `model_dump(mode="json")`s everything, `context.py:52`):

1. The **`AccountDocument`** — needed for `account.posting_prompt`, `account.personality`, `account.contrast_patterns`, `account.punctuation_rules`, `account.category`, `account.voice_version_*`, and mutated by `finalize_post` (posts_total, last_post_*). Forcing it through artifacts would drop the property accessors and the live mutation `finalize_post` performs.
2. The **`TickContext`** — passed straight to `finalize_post` (it reads `ctx.twitter`, `ctx.post_registry`, `ctx.slot`, `ctx.now_iso`, `ctx.mode`, and the locks).
3. The **`guardian`** + `max_regeneration_rounds` + `bypass_post_cooldown` — live config off the `TickContext`, engine-injected, never spec-tunable.
4. The **attribution + wiring scalars** — `run_id`, `pipeline_hash` (the loaded champion spec's `version_hash`, NOT off the account), and `copied_exclude` (the fallback-exclusion set the compose tool applies when building `ranked_refs`).

> **Note (changed from an earlier draft):** the pre-built `ranked_refs: list[GatheredTweet]` is **no longer** carried on `ActLive`. `07` deletes `reference_phase.py` and moves `ranked_refs_from_runbook` INTO `compose_until_safe`, so the tool builds the fallback list itself from the `TIMELINE_RANKED` artifact + `copied_exclude` (§5.1). `ActLive` carries only the inputs that build needs that are NOT artifacts.

> **Note (CC-7) — `followers_at_post` is NOT on `ActLive`.** It is `profile.followers_count`, produced by the SENSE `load_account_bundle` step into the `ACCOUNT_BUNDLE` artifact, so it is unknown when `07`'s runner constructs `ActLive` (that happens *before* the walk). Per canonical contract **CC-7**, `publish_post` reads it at publish time **from the `ACCOUNT_BUNDLE` artifact** — `ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE).profile.get("followers_count")` — exactly as the imperative runner reads `bundle_account["profile"]["followers_count"]` today (`runner.py:249-253`). `ActLive` carries only pre-walk-known fields, removing the pre-walk-timing problem entirely (matches `07` §2.4).

We pass these via a tiny dataclass held on `deps.live` (add `from typing import Any` and the `AccountDocument` import to `deps.py`; `TickContext` under `TYPE_CHECKING` if a cycle appears — §4.3):

```python
@dataclass
class ActLive:
    """Non-serializable handles + engine-injected config the ACT steps need, carried
    OUTSIDE ctx.data. The serializable VIEW of what these produce is the captured
    artifact (COMPOSED_POST / SAFETY_VERDICT / PUBLISHED_POST); these raw objects exist
    only for the duration of the run and are never traced or persisted.
    """

    account: AccountDocument
    tick_ctx: TickContext                 # for finalize_post (locks, slot, now_iso, mode); also the
                                          # concrete carrier of `twitter`/`post_registry` below
    guardian: Any                         # SafetyGuardian (live eval engine; never spec-tunable)
    twitter: Any                          # TwitterService — == tick_ctx.twitter (CC-7 names it explicitly)
    post_registry: Any                    # TrackedPostRepository — == tick_ctx.post_registry (CC-7)
    run_id: str                           # → creation_metrics.run_id + idempotency key (02 attribution)
    pipeline_hash: str | None = None      # loaded spec.version_hash → creation_metrics.pipeline_hash (02)
    copied_exclude: frozenset[str] = frozenset()   # fallback-exclusion set for ranked_refs build
    max_regeneration_rounds: int = 10
    bypass_post_cooldown: bool = False
```

> **Field set is canonical per CC-7.** `ActLive` carries exactly `account`, `guardian`, `twitter`, `post_registry`, `max_regeneration_rounds`, `bypass_post_cooldown`, `copied_exclude`, `pipeline_hash`, `run_id` — plus `tick_ctx`, which is the concrete `TickContext` that `finalize_post(ctx: TickContext, …)` requires (verified `post_tick.py:23-33`) and through which `twitter`/`post_registry` are reached (`twitter == tick_ctx.twitter`, `post_registry == tick_ctx.post_registry`; they are surfaced as named fields because CC-7 enumerates them). The earlier `reference_context_block`/`refs_payload`/`reference_pool` fields are **removed** — like `ranked_refs`, `compose_until_safe` now derives them **internally from SENSE artifacts** (§5.1), so they are not `ActLive` inputs. `followers_at_post` is likewise off `ActLive` (read from `ACCOUNT_BUNDLE` at publish, CC-7).

> `guardian`/`twitter`/`post_registry` are typed `Any` to avoid importing `SafetyGuardian`/`TwitterService`/`TrackedPostRepository` into `deps.py` purely for hints (they live elsewhere; `deps.py` stays infra-light). Mirrors how `TickContext` already type-hints services lazily.

> **Why a dataclass on `deps`, not new `ctx.data` keys?** Two reasons, both load-bearing. (a) `ctx.set`/`set_artifact` is the *serializable* channel — capture sinks snapshot it (`events/capture.py`), and `set_artifact` would reject a raw `AccountDocument`/`TickContext`. (b) The grounding's load-bearing truth is explicit: "non-serializable live objects … passed WITHOUT forcing them through model_dump (e.g. via deps, while the captured ARTIFACT is the serializable view)." `deps` is exactly the per-run, engine-injected, not-traced channel for that. `ActLive` is defined in this doc (`deps.py`, or a sibling `act_types.py` if a cycle appears — §4 DoD); no other doc owns it.

### 4.3 Where `ActLive` is built — `07`'s runner (this doc only specifies the field sources)

`07` deletes `reference_phase.py` and rewrites `_run_account_pipeline` into one `run_steps` walk. `07`'s runner is the single place that assembles `deps.live`. This doc does NOT write that assembly (that is `07`'s body); it only pins **where each `ActLive` field comes from** so `07` and the tools agree. All sources verified in the current imperative runner:

| `ActLive` field | Source in `07`'s runner | Verified today at |
|---|---|---|
| `account` | the reserved/reloaded `AccountDocument` | `runner.py:217` (`reservation.account`) |
| `tick_ctx` | the `TickContext` the runner already holds | `_run_account_pipeline(ctx, …)` |
| `guardian` | `tick_ctx.guardian` | `context.py:23` |
| `twitter` | `tick_ctx.twitter` (== the SENSE deps' `twitter`) | `context.py` |
| `post_registry` | `tick_ctx.post_registry` | `context.py` |
| `run_id` | `current_run_id()` (dispatcher contextvar bound by `run_events`) — same id `08`/the trace use | `dispatcher.py:90-92` |
| `pipeline_hash` | the loaded champion spec's `version_hash` (`load_or_default(aid).version_hash`, doc 04) | doc 04 §6b |
| `copied_exclude` | `copied_reference_exclude_set(account)` | `runner.py:227` |
| `max_regeneration_rounds` | `tick_ctx.max_regeneration_rounds` | `context.py:31` |
| `bypass_post_cooldown` | `tick_ctx.bypass_post_cooldown` | `context.py:32` |

> **All `ActLive` fields are pre-walk-known**, so `07`'s runner builds `deps.live` BEFORE the `run_steps` walk (matching `07` §2.4's construction). The reference-derived inputs that an earlier draft carried (`reference_context_block`/`refs_payload`/`reference_pool`) are **no longer on `ActLive`** — `compose_until_safe` derives them internally from the SENSE artifacts (`TIMELINE_ANALYSIS`/`OWN_POSTS_ANALYSIS`/`TIMELINE_REFERENCES`) at run time (§5.1 `_reference_inputs`), exactly as it derives `ranked_refs` from `TIMELINE_RANKED` + `copied_exclude`. `followers_at_post` is also off `ActLive`: `publish_post` reads it from the `ACCOUNT_BUNDLE` artifact at publish time (CC-7; `07` §2.4). This removes the "build `ActLive` after SENSE" timing dependency entirely.

> **`pipeline_hash` is NOT on the account.** Verified: `account.py` has `voice_version_hash/seq/label` accessors (`366-387`) but **no** `pipeline_version_hash`. The pipeline hash lives only on the `PipelineSpecDocument` (`pipelinespecs/{account_id}`, doc 04). `07`'s runner already loads that spec to compile it, so it reads `spec.version_hash` there and threads it into `ActLive.pipeline_hash`. Any reference (in `02`/`07`) to `account.pipeline_version_hash` is stale and must read the loaded spec's `version_hash` instead.

### Definition of Done — §4
- `PostRunDeps(...)` accepts the new `live` kwarg; existing `PostRunDeps.build()` and the (now `07`-owned) `post_run_deps_from_tick` callers still construct.
- `ActLive` imports cleanly (`AccountDocument`, `TickContext` are already importable from their modules). `ActLive` lives in `deps.py`, or a sibling `app/pipeline/services/act_types.py` if a cycle appears — pick whichever keeps `py_compile` green.

> **Import-cycle watch:** `deps.py` importing `app.interval.context.TickContext` is the only risk. If `app.interval.context` → … → `app.pipeline.services.deps` forms a cycle, define `ActLive` in `app/pipeline/services/act_types.py` with `from __future__ import annotations` + `TYPE_CHECKING` hints. Verified today: `context.py` imports only `schemas` + `models.account`; no path back to `deps`. So direct placement in `deps.py` is expected to compile — confirm with `py_compile` and fall back to `act_types.py` only if it doesn't.

---

## 5. The two new tools

### 5.1 `compose_until_safe` (LLM tool) — owns the loop

**File:** `app/pipeline/tools/llm/compose_until_safe.py`. This tool is the literal transcription of `interval/runner.py:304-365` into a tool body, **plus** the `ranked_refs` build AND the reference-context derivation (`reference_context_block`/`refs_payload`/`reference_pool`) that `07` moves out of the deleted `reference_phase.py` — all now sourced from SENSE artifacts inside the tool, not from `deps.live` (CC-7). **It must preserve the control flow exactly:** build the `ranked_refs` fallback list from the `TIMELINE_RANKED` artifact (applying `copied_exclude` and the `settings.max_reference_fallback_attempts` cap, exactly as `ranked_refs_from_runbook` does today — `reference_phase.py:49-67`), then outer loop over `ranked_refs` (fallback), inner loop over `range(max_regeneration_rounds)`, `safety_reject_reason` fed back only on `reg_round > 0`, and `is_niche_mismatch_reject` breaking the *inner* loop to advance to the next reference (verified `runner.py:321,331,354,361`).

```python
"""Coarse compose tool: owns the ranked-refs build + the ref-fallback × regeneration
loop and the guardian feedback that runner.py:304-365 runs imperatively today. Writes
COMPOSED_POST when a body passes the guardian, and always writes SAFETY_VERDICT."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.interval.compose_timeline_post import compose_formatted_post
from app.interval.reference_context import format_reference_context_for_compose
from app.agents.safety_guardian import is_niche_mismatch_reject
from app.interval.tweet_topic_preanalysis import GatheredTweet, preanalysis_from_winner
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

TOOL_ID = "llm.compose_until_safe"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Compose a post, regenerating with guardian feedback and falling back across references until one passes safety"
TOOL_READS = (ArtifactKey.TIMELINE_ANALYSIS, ArtifactKey.OWN_POSTS_ANALYSIS, ArtifactKey.TIMELINE_RANKED)
TOOL_WRITES = (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)


def _ranked_refs(ctx: TickRunContext, copied_exclude: frozenset[str]) -> list[GatheredTweet]:
    """Verbatim port of reference_phase.ranked_refs_from_runbook (reference_phase.py:49-67):
    read TIMELINE_RANKED.ranked rows, drop copied refs, cap to max_reference_fallback_attempts."""
    ranked_payload = ctx.data.get("timeline_ranked") or {}
    ranked_raw = ranked_payload.get("ranked") if isinstance(ranked_payload, dict) else []
    out: list[GatheredTweet] = []
    for row in ranked_raw or []:
        if not isinstance(row, dict):
            continue
        gt = GatheredTweet.model_validate(row)
        if gt.tweet_id in copied_exclude:
            continue
        out.append(gt)
    max_attempts = max(0, int(settings.max_reference_fallback_attempts))
    if max_attempts > 0:
        out = out[:max_attempts]
    return out


def _reference_inputs(ctx: TickRunContext) -> tuple[str, dict, list[dict]]:
    """Derive the compose-context block + reference pool from the SENSE artifacts that
    the runner used to carry on ActLive. Mirrors reference_phase.py:88,103 and
    runner.py:244-247 — now sourced from ctx, not deps.live (CC-7).

      reference_context_block  ← format_reference_context_for_compose(TIMELINE_ANALYSIS,
                                  OWN_POSTS_ANALYSIS)  (the two brief artifacts)
      refs_payload             ← TIMELINE_REFERENCES artifact (for pulled_tweet_stats)
      reference_pool           ← filter_rows_with_urls(merge_reference_pool(refs_payload))
    """
    timeline_analysis = ctx.data.get("timeline_analysis") or {}
    own_posts_analysis = ctx.data.get("own_posts_analysis") or {}
    block = format_reference_context_for_compose(timeline_analysis, own_posts_analysis)
    refs_payload = ctx.data.get("timeline_references") or {}
    if not isinstance(refs_payload, dict):
        refs_payload = {}
    reference_pool = filter_rows_with_urls(TickDataService.merge_reference_pool(refs_payload))
    return block, refs_payload, reference_pool


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    guardian = live.guardian
    account = live.account
    ranked_refs = _ranked_refs(ctx, live.copied_exclude)
    reference_context_block, refs_payload, reference_pool = _reference_inputs(ctx)
    max_rounds = max(1, int(live.max_regeneration_rounds))

    last_reject: str | None = None
    selected_body: str | None = None
    selected_round: int | None = None
    selected_ref_idx: int | None = None
    winner = None
    topic_pre = None
    references_tried = 0

    for ref_idx, candidate in enumerate(ranked_refs):
        winner = candidate
        topic_pre = preanalysis_from_winner(winner)
        references_tried += 1
        candidate_reject: str | None = None
        for reg_round in range(max_rounds):
            body = compose_formatted_post(
                winner,
                account.category,
                account_posting_prompt=(account.posting_prompt or "").strip(),
                account_personality=(account.personality or "").strip(),
                contrast_patterns=list(account.contrast_patterns or []),
                punctuation_rules=list(account.punctuation_rules or []),
                reference_context_block=reference_context_block,
                regeneration_round=reg_round,
                safety_reject_reason=candidate_reject if reg_round > 0 else None,
            )
            approved, reject = guardian.evaluate(body, niche=account.category)
            if approved:
                selected_body = body
                selected_round = reg_round
                selected_ref_idx = ref_idx
                break
            candidate_reject = reject or "safety_rejected"
            if is_niche_mismatch_reject(candidate_reject):
                last_reject = candidate_reject
                break
        if selected_body is not None:
            break
        last_reject = candidate_reject or last_reject

    # Cost reporting: NOTHING to do here. Per CC-9, the engine's cost meter (07 §4) tallies
    # LLM spend automatically — every compose_formatted_post + guardian.evaluate call (incl.
    # each regeneration round) funnels through ClaudeClient, which accumulates token cost per
    # run; 07's cost wrapper drains it after each leaf. This tool reports no cost itself and
    # sets no `_step_cost_usd` key (that earlier-draft seam is dropped — 07 §4.1).

    if selected_body is None or winner is None or topic_pre is None:
        ctx.set_artifact(
            ArtifactKey.SAFETY_VERDICT,
            {"approved": False, "last_reject": last_reject or "all_compose_attempts_failed",
             "references_tried": references_tried, "regeneration_round": 0},
        )
        # No COMPOSED_POST written → publish_post skips. Mirror today's "rejected" outcome.
        return StepResult(ok=True, skipped=True, skip_reason=last_reject or "all_compose_attempts_failed")

    source_id = topic_pre.selected_tweet_ids[0] if topic_pre.selected_tweet_ids else None
    pull_stats = refs_payload.get("pulled_tweet_stats") or {}
    source_metrics = _source_metrics_at_pick(winner)

    ctx.set_artifact(
        ArtifactKey.COMPOSED_POST,
        {
            "body": selected_body,
            "reference_index": selected_ref_idx or 0,
            "references_tried": references_tried,
            "regeneration_round": selected_round or 0,
            "source_reference_tweet_id": source_id,
            "chosen_embed_url": topic_pre.chosen_embed_url,
            "source_reference_metrics_at_pick": source_metrics,
            "tweets_pulled": len(reference_pool),
            "tweets_pulled_new": int(pull_stats.get("new_count") or 0),
            "tweets_pulled_duplicates": int(pull_stats.get("duplicate_count") or 0),
        },
    )
    ctx.set_artifact(
        ArtifactKey.SAFETY_VERDICT,
        {"approved": True, "last_reject": last_reject, "references_tried": references_tried,
         "regeneration_round": selected_round or 0},
    )
    return StepResult(ok=True, payload={"body": selected_body, "references_tried": references_tried})


def _source_metrics_at_pick(winner) -> dict | None:
    from app.metrics.derived import extract_entities, extract_text_features
    if winner is None:
        return None
    return {
        "tweet_id": winner.tweet_id,
        "popularity_score": winner.popularity_score,
        "author_followers_count": winner.metrics.get("author_followers_count"),
        "quote_count": winner.metrics.get("quote_count"),
        "impression_count": winner.metrics.get("impression_count"),
        "text_features": extract_text_features(winner.text),
        "entity_tags": extract_entities(winner.metrics),
    }
```

> **Behavior-preservation checklist (each item maps to a real line in `runner.py`, verified):**
> - `ranked_refs` build from `TIMELINE_RANKED` + `copied_exclude` + cap — ports `reference_phase.py:49-67`.
> - `_reference_inputs(ctx)`: `reference_context_block` from `format_reference_context_for_compose(TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS)` — ports `runner.py:244-247`; `refs_payload` from `TIMELINE_REFERENCES` — `reference_phase.py:88`; `reference_pool` from `filter_rows_with_urls(TickDataService.merge_reference_pool(refs_payload))` — `reference_phase.py:103`. (These were `ActLive` fields in an earlier draft; CC-7 moves them to internal artifact derivation.)
> - Outer loop over `ranked_refs` with `references_tried` counter — `runner.py:304,307`.
> - `preanalysis_from_winner(winner)` per reference — `runner.py:306`.
> - Inner `range(max_regeneration_rounds)` — `runner.py:321`.
> - `compose_formatted_post(...)` with identical kwargs — `runner.py:322-332`.
> - `safety_reject_reason=candidate_reject if reg_round > 0 else None` — `runner.py:331`.
> - `guardian.evaluate(body, niche=account.category)` — `runner.py:340`.
> - approved → record `selected_body`/`selected_round`, break inner — `runner.py:347-351`.
> - `is_niche_mismatch_reject` → set `last_reject`, break inner (advance reference) — `runner.py:354-361`.
> - `selected_body is not None` → break outer — `runner.py:363-364`.
> - all-failed → "rejected" with `references_tried` — `runner.py:367-382`.
> - `source_reference_metrics_at_pick` block — `runner.py:401-411`.

> **Bundle-trace mutation, NOT carried into the tool.** Today the runner calls `apply_preanalysis_to_account_bundle(bundle_account, topic_preanalysis)` (`runner.py:308`) — it is **trace-only** (attaches reference engagements to the bundle dict for the SSE trace, per its docstring at `tweet_topic_preanalysis.py:179-190`) and does NOT affect compose or publish. It is therefore omitted from `compose_until_safe` entirely (no `apply_preanalysis_to_account_bundle` import). If the bundle SSE trace is still wanted, `07` keeps that one call in the runner against the bundle dict per the `05`/`08` SSE-trace decision; the tool never touches it.

#### Why this is an `llm` tool and not `data`/`deterministic`
`compose_formatted_post` issues the Claude composition call(s); `guardian.evaluate` issues the niche-fit Claude call (`safety_guardian.py:42-54`). It is the canonical LLM-cost step. The engine's cost-ceiling wrapper (`07-interpreter-wiring.md` §3-4) wraps it like every other leaf — see §6. Per **CC-9**, the meter advances on **real** spend reported from `claude_client`: `07` makes `ClaudeClient` accumulate per-run token cost (every `messages.create`, incl. each regeneration round) and its cost wrapper drains that after each leaf. This tool therefore reports no cost itself — there is no `_step_cost_usd` key to set (that earlier-draft seam is dropped, `07` §4.1). The ceiling trips on compose's actual token usage automatically.

### 5.2 `publish_post` (data tool) — idempotent finalize

**File:** `app/pipeline/tools/data/publish_post.py`. Wraps `finalize_post` (`post_tick.py:23-96`) unchanged, gated by an idempotency marker so a retry cannot double-post.

```python
"""Coarse publish tool: wraps finalize_post with an idempotency marker so a retry
cannot double-post to X. Writes PUBLISHED_POST. Reads COMPOSED_POST + SAFETY_VERDICT."""

from __future__ import annotations

import logging

from app.interval.orchestration.post_tick import finalize_post
from app.models.tracked_post import PostCreationMetrics
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

TOOL_ID = "data.publish_post"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Publish the approved post to X (idempotent) and finalize account/registry state"
TOOL_READS = (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)
TOOL_WRITES = (ArtifactKey.PUBLISHED_POST,)

# Process-local idempotency ledger: (run_id, account_id) → tweet_id already posted.
_POSTED: dict[tuple[str, str], str] = {}


def _followers_at_post(ctx: TickRunContext) -> int | None:
    """CC-7: read followers_count from the ACCOUNT_BUNDLE artifact at publish time
    (it is unknown when the runner builds ActLive, pre-walk). Mirrors the imperative
    runner's bundle_account['profile']['followers_count'] read (runner.py:249-253)."""
    bundle = ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE)
    if bundle is None:
        return None
    profile = getattr(bundle, "profile", None) or {}
    fc = profile.get("followers_count")
    return fc if isinstance(fc, int) else None


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    account = live.account
    verdict = ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)
    composed = ctx.get_artifact(ArtifactKey.COMPOSED_POST)

    if verdict is None or not verdict.approved or composed is None:
        reason = (verdict.last_reject if verdict else None) or "no_approved_body"
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "posted": False, "skipped_reason": reason},
        )
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    idem_key = f"{live.run_id}:{account.account_id}"
    ledger_key = (live.run_id, account.account_id)
    if ledger_key in _POSTED:
        # A retry within the same run already posted; never double-post. Reconstruct a
        # minimal legacy-shaped result so the runner's _result_from_run still sees a
        # `tweet` object (07 §2.6 reads PUBLISHED_POST.result).
        replay_id = _POSTED[ledger_key]
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "tweet_id": replay_id,
             "posted": True, "idempotency_key": idem_key, "note": "idempotent_replay",
             "regeneration_round": composed.regeneration_round,
             "result": {"account_id": account.account_id, "tweet": {"id": replay_id},
                        "regeneration_round": composed.regeneration_round,
                        "note": "idempotent_replay"}},
        )
        return StepResult(ok=True, payload={"idempotent_replay": True})

    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        tweets_pulled=composed.tweets_pulled,
        tweets_pulled_new=composed.tweets_pulled_new,
        tweets_pulled_duplicates=composed.tweets_pulled_duplicates,
        regeneration_round=composed.regeneration_round,
        source_reference_tweet_id=composed.source_reference_tweet_id,
        chosen_embed_url=composed.chosen_embed_url,
        voice_version_hash=account.voice_version_hash,
        voice_version_seq=account.voice_version_seq,
        voice_version_label=account.voice_version_label,
        source_reference_metrics_at_pick=composed.source_reference_metrics_at_pick,
        # Attribution join (the fields 02 adds to PostCreationMetrics). run_id is the
        # dispatcher run id threaded onto ActLive; pipeline_hash is the LOADED champion
        # spec's version_hash (NOT account.pipeline_version_hash — that accessor does
        # not exist). HARD PREREQ: 02's field add must be merged first, else these two
        # kwargs raise (extra field). See §5.2 Attribution note below.
        run_id=live.run_id,
        pipeline_hash=live.pipeline_hash,
    )

    result = finalize_post(
        live.tick_ctx,
        account,
        composed.body,
        regeneration_round=composed.regeneration_round,
        earlier_reject=verdict.last_reject,
        creation_metrics=creation_metrics,
        source_reference_tweet_id=composed.source_reference_tweet_id,
        followers_at_post=_followers_at_post(ctx),   # CC-7: from ACCOUNT_BUNDLE, not deps.live
    )

    tweet_id = None
    tw = result.get("tweet") if isinstance(result, dict) else None
    if isinstance(tw, dict):
        tweet_id = str(tw.get("id") or "") or None
    if tweet_id and "error" not in result:
        _POSTED[ledger_key] = tweet_id

    ctx.set_artifact(
        ArtifactKey.PUBLISHED_POST,
        {
            "account_id": account.account_id,
            "tweet_id": tweet_id,
            "posted": "error" not in result,
            "regeneration_round": composed.regeneration_round,
            "idempotency_key": idem_key,
            "note": result.get("note"),
            "skipped_reason": str(result.get("error")) if "error" in result else None,
            "result": result,                 # the FULL finalize_post dict — runner returns this
        },
    )
    if "error" in result:
        return StepResult(ok=False, skip_reason=str(result.get("error")), payload=result)
    return StepResult(ok=True, payload=result)
```

> **Skip path also carries a `result`.** When `compose` produced no approved body, the skip-branch `PUBLISHED_POST` write should include `result={"account_id": account.account_id, "rejected": reason}` so `07`'s `_result_from_run` (which prefers `verdict.last_reject` for the `rejected` dict) and a direct read of `published.result` agree. The runner reads the `SAFETY_VERDICT` first for the rejected/skipped classification, so the publish `result` here is a belt-and-suspenders echo, not the primary signal.

#### Idempotency marker — Decision Defense
Publish is non-idempotent against X: `finalize_post` calls `ctx.twitter.post_tweet` exactly once (`post_tick.py:36`) with no precomputed id / If-Match (the grounding flags this explicitly). The marker is a **process-local ledger keyed `(run_id, account_id)`**, checked before the X call and stamped after. Rationale for *this* design (the elegant/simpler option) over alternatives:

- **vs. a RavenDB lock document:** the system already holds a per-account RavenDB lock + file lock + thread lock for the *whole* post pipeline (`post_guard.py`, `slot_claim.py`), released only on `finalize_post` success/failure. Concurrent ticks on the same account cannot both reach `publish_post` — the guards serialize them. The double-post risk the marker addresses is specifically a **retry of the SAME run** (the interpreter re-invoking the step after a hang/exception), and `(run_id, account_id)` is the exact key for that. A second Raven doc would duplicate locking we already have and add a partial-write window. The interpreter does NOT need CAS (per settled architecture).
- **`run_id` is stable per run:** `run_account_pipeline` mints `run_id = ctx.forced_run_id or uuid4().hex` once (`runner.py:141`) and it is the same id the trace/SSE use. Reusing it as the idempotency key means the marker and the trace agree.
- **Scope of "retry":** the interpreter today has no resume/replay loop, so the ledger guards the one real path — an in-process re-entry of `publish_post` within the same `run_steps` call. The ledger is intentionally process-local and ephemeral (lost on restart); a restart starts a new `run_id` and the slot/cooldown guards prevent re-posting the same interval. This is sufficient and minimal; do not over-build a durable dedup store.

#### Attribution stamping — Decision Defense (resolves the `pipeline_hash` ownership gap)
`publish_post` is the single site that stamps `run_id` + `pipeline_hash` onto `creation_metrics`. Three facts pin the values, all verified:
- **`run_id`** = `live.run_id`, which `07`'s runner sets from `current_run_id()` (`dispatcher.py:90-92`) — the same id the trace (`08`) and SSE use. This is also the idempotency-ledger key, so post, trace, and dedup all agree on one id.
- **`pipeline_hash`** = `live.pipeline_hash`, which is the **loaded champion spec's `version_hash`** (`PipelineSpecRepository.load_or_default(aid).version_hash`, doc 04 §6b), read by `07`'s runner at compile time. It is **NOT** `account.pipeline_version_hash` — that accessor does not exist (`account.py` has only `voice_version_*`, `366-387`). Any sibling doc (`02` §3.3, `07` §7) that reads `account.pipeline_version_hash` is stale and must read the loaded spec's `version_hash`; this doc's `live.pipeline_hash` is the canonical carrier.
- **Hard prerequisite (sequencing):** the two kwargs `run_id=`/`pipeline_hash=` require the `PostCreationMetrics` field additions that `02` owns (`tracked_post.py:10-25`). `02` is sequenced before this doc in `13-verification-and-sequencing.md` §2 (order `… 04 → 05 → 02 → 08 → 06 → 07`), so by the time `06/07` land the fields exist. If for any reason `06` is built before `02`, constructing `PostCreationMetrics(run_id=…, pipeline_hash=…)` raises (extra field) — do not implement `publish_post` until `02`'s field add is merged.

`finalize_post` forwards `creation_metrics` to `record_post` unchanged (`post_tick.py:59-65`); no edit to `finalize_post`/`record_post` is needed for the join — it travels inside the existing object.

#### `followers_at_post` — read from the `ACCOUNT_BUNDLE` artifact (CC-7)
`followers_at_post` is NOT on `deps.live`: per canonical contract **CC-7**, `publish_post` reads it at publish time from the `ACCOUNT_BUNDLE` artifact (`_followers_at_post(ctx)` → `bundle.profile.get("followers_count")`), because the value is produced by the SENSE `load_account_bundle` step and is therefore unknown when `07`'s runner builds `ActLive` *before* the walk. This is the same value the imperative runner extracts (`runner.py:249-253`) and matches `07` §2.4's resolution. `ACCOUNT_BUNDLE` is read **internally** — it is intentionally NOT added to the step's declared `reads` (which stay `(COMPOSED_POST, SAFETY_VERDICT)` per §7.1, the seed read-set `05`'s R3 grades), exactly as `compose_until_safe` reads the live `account`/`guardian` off `deps.live` without declaring them. The artifact is guaranteed present because `load_account_bundle` is the first SENSE leaf and always runs before `publish_post` in the compiled graph.

### Definition of Done — §5
- Both tool files `py_compile` clean.
- `compose_until_safe.run` builds `ranked_refs` from `TIMELINE_RANKED` (+ `copied_exclude` + `max_reference_fallback_attempts` cap) and derives `reference_context_block`/`refs_payload`/`reference_pool` internally from the SENSE artifacts (`_reference_inputs`, §5.1) — none of these come from `deps.live`; writes `SAFETY_VERDICT` on every path, and `COMPOSED_POST` only when approved.
- `publish_post.run` calls `finalize_post` at most once per `(run_id, account_id)`; a second invocation with the same key writes `PUBLISHED_POST` with `note="idempotent_replay"` and does NOT call `post_tweet` again. It reads `followers_at_post` from the `ACCOUNT_BUNDLE` artifact (CC-7), not from `deps.live`.
- On the happy path, `PUBLISHED_POST.result` holds the FULL `finalize_post` dict (so `'tweet' in published.result`), and `creation_metrics.run_id == live.run_id` / `creation_metrics.pipeline_hash == live.pipeline_hash` (requires `02`'s field add merged).
- Skipping (no approved body) writes `PUBLISHED_POST{posted: False, skipped_reason, result}` and returns a skipped `StepResult`.

---

## 6. The guardian appears twice — and that is correct

There are two distinct guardian roles; conflating them is the trap.

| Role | Where | Purpose | Bypassable? |
|---|---|---|---|
| **Compose-loop driver** | inside `compose_until_safe` (this doc) | feeds reject-reason back into regeneration; decides niche-mismatch fallback | it IS the loop; a spec can tune `max_regeneration_rounds` but never remove the guardian call |
| **Engine post-hoc invariant** | `run_steps` leaf wrapper (`07-interpreter-wiring.md` §3) | non-bypassable safety assertion + cost ceiling around EVERY leaf | never expressible/removable in a spec |

This doc owns only the first. The engine wrapper (`07`) wraps `compose_until_safe` like any other leaf; `07`'s `guardian_wrapper` keys on `flat.id == "compose_until_safe"` (correct — compose is a top-level step, so `flatten_steps` yields the bare id, `flow.py:103-124`) and asserts that `SAFETY_VERDICT` was written — a cheap, idempotent invariant confirmation, not a behavior change. **Do not** add the cost-ceiling/guardian wrapper logic in this doc — that is `07`'s slice. This doc must not let a spec author disable the guardian: the guardian arrives via `deps.live.guardian` (engine-injected on `ActLive`, §4.2), never as a tool kwarg an LLM/spec could null out.

---

## 7. What this doc contributes to the runner (the runner rewrite itself is `07`)

`07` owns the rewrite of `_run_account_pipeline` into ONE `run_steps` walk of the compiled spec, the deletion of `reference_phase.py`, and `_result_from_run` (terminal-artifact → legacy-return mapping). This doc contributes exactly three things the new runner consumes: (7.1) the two ACT `Step`s appended to the runbook, (7.2) the two thin `services/steps.py` wrappers, and (7.5) the test edits this doc's runbook append forces. Everything about *driving* those steps — building `deps.live`, calling `run_steps`, mapping artifacts back to the return dict — is `07`'s body, not this doc's. The earlier draft's imperative two-step drive is **superseded** and is not the target code.

### 7.1 The runbook ends with the two ACT steps (`runbooks/post_tick.py`)

Append after the `summarize_for_compose` parallel block (after line 84, inside the tuple):

```python
    Step(
        "compose_until_safe",
        steps.compose_step,
        reads=(ArtifactKey.TIMELINE_ANALYSIS, ArtifactKey.OWN_POSTS_ANALYSIS, ArtifactKey.TIMELINE_RANKED),
        writes=(ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT),
        purpose="Compose with guardian feedback + reference fallback until safe",
    ),
    Step(
        "publish_post",
        steps.publish_step,
        reads=(ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT),
        writes=(ArtifactKey.PUBLISHED_POST,),
        purpose="Publish to X (idempotent) and finalize state",
    ),
```

> **The `compose_until_safe` `reads` tuple is canonical here: `(TIMELINE_ANALYSIS, OWN_POSTS_ANALYSIS, TIMELINE_RANKED)`.** This is the ONE authoritative read set the seed spec (doc 04) carries and `05`'s validator R3 grades against. `TIMELINE_RANKED` is included because the tool now builds `ranked_refs` from that artifact (§5.1) — it is a real upstream dependency (written by `rank_external_references`), so R3 passes and the flow-diagram edge is honest. (`07` §2.3 lists the same three; this resolves the earlier 2-vs-3 read-set divergence — match this tuple everywhere.) The `reads` are *declared* for the trace graph / mermaid (`flow.py:48-91` unions them on composites; leaves carry their own); the live `AccountDocument`/`guardian` inputs still arrive via `deps.live` (non-serializable). **Frontend sync:** add `compose_until_safe` + `publish_post` nodes to `frontend/src/lib/pipeline/flowGraph.ts` matching these bare dotted ids (top-level → no prefix) — the runbook header at `post_tick.py:6-11` mandates this. Replaces the ad-hoc `compose`/`safety`/`publish`/`complete` orchestrator nodes. **Seed-spec sync:** doc 04's `spec_from_runbook` walks `POST_TICK_REFERENCE_STEPS`, so once this append lands the seed produces 10 leaves, not 8 — doc 04's `STEP_TOOL_MAP` must gain `compose_until_safe → "llm.compose_until_safe"` and `publish_post → "data.publish_post"` (this doc owns the two `TOOL_ID` strings; doc 04 owns wiring them into the seed). This is the resolution to the "who appends the ACT leaves to the seed" hand-off.

### 7.2 Thin wrappers (`pipeline/services/steps.py`)

```python
def compose_step(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    from app.pipeline.tools.llm import compose_until_safe
    return compose_until_safe.run(ctx, deps)


def publish_step(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    from app.pipeline.tools.data import publish_post
    return publish_post.run(ctx, deps)
```

> These wrappers are intentionally trivial — the tools already take `(ctx, deps)` directly (unlike the SENSE tools whose wrappers spread `deps` fields into many kwargs). Keeping the wrapper indirection matches the house pattern ("the real wiring lives in `services/steps.py`") and keeps the runbook importing only `steps.*`.

### 7.3 The hand-off to `07`'s runner (informative — `07` writes this body)

> **SUPERSEDED by `07` (one-walk).** Any earlier-draft sketch in which `06` *drove* the ACT steps itself — an imperative two-step drive over a `run_reference_phase`/`ReferencePhaseResult` seam, or a runner that assembles `ActLive` mid-walk *after* SENSE — is **superseded by `07` §2.4**. There is exactly ONE runner shape: `07`'s single `run_steps(graph, …)` walk of the whole compiled spec (SENSE + ACT). The paragraph below is purely informative tracing of `07`'s shape; `06` prescribes none of the runner body.

For implementers tracing the data flow, `07`'s rewritten `_run_account_pipeline` walks the WHOLE compiled spec in one `run_steps(graph, run_ctx, deps, wrappers=engine_invariants(...))` call. Because every `ActLive` field is now pre-walk-known (the reference-derived inputs moved INTO `compose_until_safe`, §4.3/§5.1, and `followers_at_post` is read from `ACCOUNT_BUNDLE` at publish), `07` builds `deps.live = ActLive(...)` **once, before** the `run_steps` call (matching `07` §2.4) — there is no "assemble `ActLive` after SENSE" step. After the walk, `07`'s `_result_from_run` reads:
- `SAFETY_VERDICT` → if `None`/`not approved`, return `{"account_id": aid, "rejected": verdict.last_reject or "all_compose_attempts_failed"}` (plus `references_tried` from the verdict, matching today's `runner.py:367-382`);
- else `PUBLISHED_POST.result` → return it verbatim (the full `finalize_post` dict, so `'tweet' in out` holds — `PublishedPost.result` is canonical per **CC-4**).

This doc guarantees the two artifacts the runner reads are written on every path (§5 DoD). It does **not** prescribe the runner body — that is `07`.

### 7.4 Dead imperative code `07` removes (for cross-reference only)

When `07` rewrites the runner it deletes: the inner compose/regeneration loop (`runner.py:304-365`), the manual `creation_metrics` construction (`runner.py:412-424` — its fields now flow `COMPOSED_POST` → `publish_post`), and the direct `finalize_post` call (`runner.py:426-435`). The bundle-trace `apply_preanalysis_to_account_bundle` call (`runner.py:308`) is trace-only and is kept-or-dropped per the `05`/`08` SSE-trace decision. The slot-reservation and `try/finally: release_post_pipeline_guards` (`runner.py:442-443`) stay. **This deletion is `07`'s edit, not this doc's** — listed here only so the two docs describe the same end-state.

### Definition of Done — §7 (this doc's contribution)
- `POST_TICK_REFERENCE_STEPS` flattens to the 8 SENSE leaves + `compose_until_safe` + `publish_post` (10 entries via `flatten_steps`).
- The two ACT `Step`s import `steps.compose_step`/`steps.publish_step`; both wrappers exist and forward `(ctx, deps)`.
- `flowGraph.ts` has `compose_until_safe` + `publish_post` nodes; dashboard lights them.
- doc 04's `STEP_TOOL_MAP` maps the two new ids to the `TOOL_ID`s this doc defines.
- The runbook-id unit tests are updated (§7.5) so `pytest` is green at the close of the `06→07` unit.

### 7.5 Tests this doc's runbook append breaks (must be updated, not left RED)

Appending the two ACT steps changes `flatten_steps(POST_TICK_REFERENCE_STEPS)` from 8 → 10 leaves and the top-level tuple from 5 → 7 entries. Two suites assert these exact lists and WILL go RED the instant §7.1 lands — they are part of the `06→07` import-break unit and must be swept inside it (per `13` §1's expected-RED rule):

- **`tests/unit/test_pipeline_runbook.py`** (verified): `test_runbook_step_names_are_readable` (line 17, asserts `names == [the 8 SENSE ids]`) → append `"compose_until_safe"`, `"publish_post"` to the expected list. `test_runbook_top_level_step_ids` (line 31, asserts the 5 top-level ids ending `"summarize_for_compose"`) → append `"compose_until_safe"`, `"publish_post"`. `test ... run_steps(POST_TICK_REFERENCE_STEPS, ...)` (line 71) now also executes the two ACT steps — give the test a `deps.live = ActLive(...)` (or stub `compose_step`/`publish_step`) so it does not hit the live X/Claude path.
- **`tests/test_orchestrator.py`** (verified): patches `app.interval.runner.compose_formatted_post` (lines 92, 151, 247) — after `06/07` move the `compose_formatted_post` call INTO `compose_until_safe`, that patch target no longer affects execution. **Re-point the patch to `app.pipeline.tools.llm.compose_until_safe.compose_formatted_post`.** The assertions `'tweet' in out` (109, 165, 263) and `repo.load("a2").posts_total == 1` (110, 118, 264) stay valid because `publish_post`→`finalize_post` still returns the full `tweet` dict (carried on `PUBLISHED_POST.result`, §5.2). This suite is the largest behavior-preservation check; it is NOT in `07`'s §5 migration list (which covers only the `reference_phase.py` casualties) — add it here.

> `07` separately migrates the `reference_phase.py` casualties (`tests/test_reference_fallback.py`, `tests/unit/test_reference_phase.py`, `tests/test_runner_post_guard.py`) when it deletes that module — those are `07`'s test moves, listed in `07` §5.

---

## 8. End-to-end behavior preservation matrix

| Old (imperative) | New (typed) | Equivalent because |
|---|---|---|
| `ranked_refs_from_runbook` build (`reference_phase.py:49-67`) | `_ranked_refs(...)` inside `compose_until_safe` | same `TIMELINE_RANKED` read, same `copied_exclude` filter, same `max_reference_fallback_attempts` cap |
| outer ref loop + inner regen loop (`runner.py:304-365`) | inside `compose_until_safe.run` | same loop bodies, same break conditions, transcribed line-for-line (§5.1 checklist) |
| `creation_metrics` built in runner (`runner.py:412-424`) | built in `publish_post` from `COMPOSED_POST` | identical fields; source metrics captured in artifact |
| `finalize_post(...)` (`runner.py:426-435`) | called once inside `publish_post` | same call, same args, now idempotency-gated |
| rejected → `{rejected, references_tried}` (`runner.py:367-382`) | `SAFETY_VERDICT.approved=False` → `07`'s `_result_from_run` builds the same dict | fields preserved |
| success return `{account_id, tweet, regeneration_round, …}` (`runner.py:439-441` / `post_tick.py:86-90`) | `PUBLISHED_POST.result` returned verbatim by `_result_from_run` | full `finalize_post` dict carried on `.result`; `'tweet' in out` holds |
| voice attribution `voice_version_*` on metrics | same, in `publish_post` | reads `account.voice_version_*` accessors (`account.py:366-387`) |
| (was missing) `run_id` + `pipeline_hash` on metrics | added in `publish_post` from `live.run_id` / `live.pipeline_hash` | the attribution join (02); fields added to `PostCreationMetrics` by 02 |
| double-post on retry (latent bug) | blocked by `(run_id, account_id)` ledger | the one new behavior, intentionally additive |

---

## 9. Assumptions & open risks
All resolved; recorded here so the implementer knows where the cross-doc seams are.
- **`pipeline_hash` source:** `live.pipeline_hash` = the loaded champion spec's `version_hash` (doc 04), threaded by `07`'s runner — NOT `account.pipeline_version_hash` (that accessor does not exist). Settled in §4.3 and §5.2.
- **Attribution field prereq:** `publish_post` sets `run_id=`/`pipeline_hash=` on `PostCreationMetrics`; those fields are added by `02`, which is sequenced before `06` (`13` §2). Do not build `06` against today's model.
- **Runner ownership:** the runner rewrite, `reference_phase.py` deletion, `run_steps` wrappers, `CostMeter`, and `_result_from_run` are `07`'s — this doc only adds the two tools, three artifacts, `ActLive`, and the runbook/step-wrapper edits (§7). Resolved per `13` §2.
- **Cost reporting (CC-9):** `compose_until_safe` reports no cost itself — `07` makes `ClaudeClient` accumulate per-run token cost and its cost wrapper drains it after each leaf, so the ceiling trips on real compose spend automatically. The earlier `ctx.data["_step_cost_usd"]` seam is dropped (`07` §4.1). Flagged in §5.1.
- **`deps.live` placement:** assumes no import cycle from `deps.py` → `interval.context`; fall back to `act_types.py` if `py_compile` disagrees (§4.3 "Import-cycle watch").

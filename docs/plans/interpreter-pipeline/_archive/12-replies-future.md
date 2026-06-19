# Doc 12 — Replies as a Second Pipeline (separable, optional)

> **Status:** SEPARABLE / OPTIONAL — **not** a prerequisite for the Interpreter. Authored cold against the live tree on `feat/platform-overhaul`; every API/field/signature below was verified against the actual files (paths + line numbers are real as of authoring). Pick this up **only after** the core Interpreter (docs 03–08) is shipped and green; it adds a *second* posting behavior **using** that system, it does not modify it.
> **Scope:** Backend only. Three new catalog tools (`mentions_fetch`, `reply_compose`, `reply_publish`) + four new `services/steps.py` wrappers (`fetch_mentions`, `rank_mentions` [reusing the `deterministic.reference_rank` tool], `reply_compose_step`, `reply_publish_step` — §4.6), five new `ArtifactKey`s + Pydantic models, a small additive extension to the X client (one optional `in_reply_to` arg + a `get_mentions` read), a *reply* `PipelineSpecDocument` (its own schedule + policy), a DECIDE gate (`reply | skip`), and one new scheduler job. **No existing tool, the compiler, the validator, the engine, or the post pipeline is rewritten** — the only additive touches to existing modules are: 4 wrapper-binding rows in the compiler's `_WRAPPER_BY_STEP_ID` (doc 05 §6.0), a `kind="post"` kwarg + a `kind → (verdict_key, terminal_key)` row in the validator's R6/R7 (the kind is passed in, since the spec model carries no kind field — CC-12; spec'd in this doc §7), and one step-id in doc 07's guardian wrapper. **The spec model (`app/models/pipeline_spec.py`) is NOT edited** — the reply family is selected by the `kind="reply"` argument doc 04 already added to `document_id`/`load`/`save` (CC-12). All are small additive changes, none changes existing post behavior.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB, in-process APScheduler threadpool, synchronous tick — NOT async).

---

## 0. Read this first: why this doc is OPTIONAL and what "separable" means

The whole point of the Interpreter (docs 03–08) is that an account's pipeline is **editable DATA** — an ordered list of catalog-tool wirings (`PipelineSpecDocument`) executed by ONE generic interpreter (`compile_spec` → `run_steps`). That architecture was designed so a *second* behavior — replying to mentions — is **just another spec**, not a new engine.

This doc proves that claim concretely and then **stops**. It is the demonstration that the architecture is reply-ready. Building it is a deliberate, later choice. Three things make it cleanly separable:

1. **It adds only catalog tools + a spec.** The builder/self-rewrite rule (project constraint) is *"only WIRE + CONFIGURE existing catalog tools; never write new tool code."* A reply pipeline needs new *tools* (one-time engineering, this doc), after which a reply spec is pure data the same builder can tune. Nothing in docs 03–08 changes shape.
2. **It reuses the entire execution spine.** `compile_spec` (doc 05), `validate_spec` (doc 05), `run_steps` + the cost/guardian invariant wrappers (doc 07), and the full-fidelity `StepTraceSink` (doc 08) all work on the reply spec — a reply run traces, costs-meters, and guards itself exactly like a post run, **because it is the same interpreter walking different data.** The cost meter and `StepTraceSink` are byte-for-byte unchanged; the validator R6/R7 and the guardian wrapper each gain ONE kind/step-id row (§7/§6) so they recognize the reply terminal/verdict — additive, not a rewrite.
3. **Its trigger is independent.** Posts fire on the interval tick (`run_interval_job`, `main.py:51-58`); replies fire on a *separate* cron job this doc adds (`main.py` scheduler, §6). Neither blocks the other; turning the reply job off (one settings flag) removes the behavior entirely with zero impact on posting.

> **If you are here to ship the Interpreter, you are done — do not implement this.** The sections below are the unambiguous blueprint for *when* replies are picked up, so there are zero open questions then.

---

## 1. The shape: a reply is the same four phases, different tools

A post pipeline today is: **SENSE → DECIDE → ACT**. A reply pipeline is the *identical* shape; only the tools at each phase differ.

| Phase | Post pipeline (docs 03–07) | Reply pipeline (this doc) |
|---|---|---|
| SENSE (data) | `account_profile` → `search_fetch` → `own_posts_fetch` → rank/brief | `account_profile` (REUSED) → **`mentions_fetch`** (new) → rank the mentions worth answering |
| DECIDE (gate) | implicit (a ranked reference exists or the run skips) | **explicit `reply | skip` gate** inside `reply_compose` — most mentions are not worth a reply |
| ACT-compose (llm) | `compose_until_safe` | **`reply_compose`** (new) — composes a reply *to a specific mention*, guardian-checked, with the same regen-on-reject loop |
| ACT-publish (data) | `publish_post` (writes a root tweet) | **`reply_publish`** (new) — publishes **in reply to** the mention's tweet id, idempotent |

The reply spec's compiled `Step` tuple:

```
SENSE:
  load_account_bundle    (REUSED tool: data.account_profile)        writes ACCOUNT_BUNDLE
  fetch_mentions         (NEW tool:   data.mentions_fetch)          reads  ACCOUNT_BUNDLE   writes MENTIONS
  rank_mentions          (REUSED tool: deterministic.reference_rank) reads MENTIONS         writes MENTIONS_RANKED
DECIDE+ACT-compose:
  reply_compose          (NEW tool: llm.reply_compose)              reads  MENTIONS_RANKED  writes REPLY_DRAFT, REPLY_VERDICT
ACT-publish:
  reply_publish          (NEW tool:   data.reply_publish)           reads  REPLY_DRAFT, REPLY_VERDICT  writes REPLY_RESULT
```

> **Step ids are the bare names `fetch_mentions` / `rank_mentions` / `reply_compose` / `reply_publish`** (matching the seed §5.3, the compiler `_WRAPPER_BY_STEP_ID` rows §4.6, the guardian-wrapper widening §6, and the frontend §8) — NOT `reply_compose_until_safe`. The tool is `llm.reply_compose`; the step that wires it is `reply_compose`.

`reply_compose` owns the DECIDE gate (`reply | skip`) **and** the irreducible compose→guardian→regenerate loop in ONE coarse tool — exactly as `compose_until_safe` (doc 06) does for posts. We do **not** model "decide whether to reply" as a separate typed step: it is a cheap branch the compose tool takes before the first LLM call (a mention that scores below a config threshold → write a `skip` verdict, no compose). This keeps the graph data at the meaningful grain (SENSE steps + one compose + one publish), the same grain doc 06 settled on.

> **Decision Defense — why `rank_mentions` reuses `deterministic.reference_rank` (the TOOL) but needs its own `steps.py` WRAPPER.** `reference_rank.run(ctx, *, rows, top_n, exclude_ids, store_key)` (verified `tools/deterministic/reference_rank.py:23`) ranks any list of tweet-row dicts by interaction score and writes to a `store_key`-resolved artifact (`artifact_key_for_ctx_key(store_key)`, verified `reference_rank.py:36`). Mentions are tweet rows with the same engagement fields, so the *tool* is reused unchanged. But two of its inputs — `rows` and `store_key` — are `config_origin=="wired"` (doc 03 §4.4): they are supplied by a `services/steps.py` wrapper, **never** by spec config (doc 05 R2 rejects a `store_key` key on `StepSpec.config`). The post path already proves this: `rank_external_references` and `rank_own_posts` are *two distinct wrappers* around the same `deterministic.reference_rank` tool, each hard-coding its own `store_key` (`steps.py:139` `TIMELINE_RANKED`, `steps.py:215` `OWN_POSTS_RANKED`) and deriving its own `rows`. **Replies follow that exact pattern: add a third wrapper `rank_mentions` (§4.6)** that reads `MENTIONS`, derives `rows`, supplies `store_key="mentions_ranked"`, and passes the reply-specific `exclude_ids` (the per-account "replied mention ids" set, the reply analogue of `copied_reference_exclude_set`). The compiler binds it by step id, exactly as it binds the two post rankers (doc 05 §6.0). **Reuse the ranker tool; add a `rank_mentions` wrapper that supplies the wired `store_key`/`rows`/`exclude_ids`.**

---

## 2. The four-phase reality the implementer must respect (verified against live code)

Three facts from the live tree shape every decision below. They are the reply analogue of doc 06's "load-bearing truth."

### 2.1 There is NO mentions-fetch capability today — `mentions_fetch` needs a real data path
Verified: the X read surface is `search_recent_tweets`, `get_following_timeline_tweets`, `get_post_data`, `get_posts_data`, `get_account_data`, `get_trends` (`app/social/protocol.py:17-69`, `app/social/service.py`, `app/services/twitter_service.py`). **None fetches mentions.** So `mentions_fetch` is not a thin wrapper over an existing method — it needs a new read on the X client (Tweepy `get_users_mentions` / the mentions timeline). This is the **one genuinely new piece of platform I/O** in this doc and the reason replies are "new tools," not "new data." See §4.1 for the exact additive method.

### 2.2 Publish is NON-idempotent and post-shaped — `reply_publish` must NOT reuse `finalize_post` verbatim
`finalize_post` (`post_tick.py:23-96`, verified) does post-specific bookkeeping that is **wrong for a reply**: it bumps `account.posts_total` (line 50), sets `account.last_interval_slot = ctx.slot` (line 52), stamps `account.last_post_*` (lines 53-55), records a *copied reference* (line 56), finalizes the **interval slot reservation** (line 84), and takes a profile snapshot (line 76). A reply is not an interval post — it must not consume the posting slot, must not overwrite "last post," and is keyed to a *mention*, not a copied reference. **`reply_publish` calls a NEW, smaller `finalize_reply` (§4.4)** that publishes in-reply-to, records the reply in the registry, and stamps attribution — and does none of the slot/posts_total/copied-reference mutations. The underlying X call (`create_post`) is non-idempotent (`x_client.py:555-564`, one `create_tweet`, no precomputed id), so `reply_publish` carries the same process-local `(run_id, account_id)` idempotency ledger pattern doc 06 defined for `publish_post`.

### 2.3 `create_post` does not accept a reply target — one additive arg is required
Verified: `create_post(self, text: str)` (`protocol.py:47`, `service.py:69`, `x_client.py:555`) has no `in_reply_to`. The underlying Tweepy `create_tweet` supports `in_reply_to_tweet_id`. The **minimal, surgical** change is an *optional* `in_reply_to: str | None = None` kwarg threaded through `XTwitterClient.create_post` → `SocialMediaService.create_post` → `TwitterService.post_tweet` (§4.1). It defaults to `None`, so **every existing caller (the whole post path) is byte-for-byte unaffected** — `create_tweet(text=...)` is called exactly as today when `in_reply_to` is absent.

---

## 3. File-by-file change index

### NEW (tools + models + the reply spec wiring)

| File | Role (one line) |
|---|---|
| `app/pipeline/tools/data/mentions_fetch.py` | Data tool: fetch recent mentions of the account from X; write `MENTIONS`. (§4.2) |
| `app/pipeline/tools/llm/reply_compose.py` | Coarse LLM tool: the `reply\|skip` DECIDE gate + compose-to-mention with guardian feedback; writes `REPLY_DRAFT` (on reply) + `REPLY_VERDICT` (always). (§4.3) |
| `app/pipeline/tools/data/reply_publish.py` | Data tool: publish the reply in-reply-to the mention (idempotent) via `finalize_reply`; writes `REPLY_RESULT`. (§4.4) |
| `app/interval/orchestration/reply_tick.py` | `finalize_reply(...)` — the reply analogue of `finalize_post`, without the slot/posts_total/copied-reference mutations. (§4.4) |
| `app/jobs/reply_job.py` | `run_reply_job()` — APScheduler entrypoint that runs the reply pipeline for active accounts on the reply cadence. (§6) |
| `app/interval/reply_runner.py` | `run_reply_pipeline(ctx, account)` — the thin per-account reply driver (mirror of `run_account_pipeline`, replies spec instead of posts spec). (§6) |
| `scripts/seed_reply_spec.py` | One-time seed of the reply `PipelineSpecDocument` (status=`champion`), saved via `PipelineSpecRepository().save(spec, kind="reply")`. (§5) |

### CHANGED (small, additive; none rewrites existing behavior)

| File | Change |
|---|---|
| `app/pipeline/types/artifacts.py` | Add 5 `ArtifactKey`s (`MENTIONS`, `MENTIONS_RANKED`, `REPLY_DRAFT`, `REPLY_VERDICT`, `REPLY_RESULT`) + Pydantic models + `ARTIFACTS` entries. `MENTIONS_RANKED` reuses `RankedReferencesPayload` (see §4.5 note). (§4.5) |
| `app/social/protocol.py` | `create_post` gains optional `in_reply_to: str \| None = None`. (§4.1) |
| `app/social/service.py` | `SocialMediaService.create_post` forwards `in_reply_to`. (§4.1) |
| `app/social/implementations/x_client.py` | `XTwitterClient.create_post` passes `in_reply_to_tweet_id` to `create_tweet` when set; **plus** a new `get_mentions(...)` read. (§4.1) |
| `app/services/twitter_service.py` | `post_tweet` gains optional `in_reply_to`; **plus** a new `get_mentions(account_id, ...)` method. (§4.1) |
| `app/models/pipeline_spec.py` | **NO CHANGE** — the model is unchanged (CC-12: `kind` is a repository-level namespace, not a model field; `document_id`/`load`/`save` already take `kind="post"` in doc 04). (§5.1) |
| `app/core/config.py` | Add reply schedule + policy settings (`reply_enabled`, `reply_poll_minutes`, `reply_max_per_run`, `reply_min_mention_score`, `reply_quiet_hours_*` reuse). (§5.2) |
| `app/main.py` | Register `run_reply_job` on its own cron when `settings.reply_enabled`. (§6) |
| `app/pipeline/spec/catalog.py` | Add the 3 new tool modules to `_TOOL_MODULES` + their wrapper rows to `_TOOL_RUN` (`data.mentions_fetch`/`llm.reply_compose`/`data.reply_publish`). NO `invariant_tool` marking — doc 05's R6/R7 detect the reply terminal/guardian tools by catalog `writes` (`reply_result`/`reply_verdict`), not a flag (§7). (§7) |
| `app/pipeline/services/steps.py` | Add 4 thin wrappers: `fetch_mentions`, `rank_mentions` (reuses `deterministic.reference_rank`, supplies wired `store_key`/`rows`/`exclude_ids`), `reply_compose_step`, `reply_publish_step`. (§4.6) |
| `app/pipeline/spec/compiler.py` (doc 05) | Add 4 rows to `_WRAPPER_BY_STEP_ID` binding the reply step ids to the wrappers above. (§4.6) |
| `app/pipeline/spec/validator.py` (doc 05) | Add a `kind="post"` kwarg to `validate_spec` and parameterize R6/R7 by it via a `kind → (verdict_key, terminal_key)` table. (§7) |
| `app/interval/runner.py` `engine_invariants` guardian wrapper (doc 07 §3.2) | Widen the step-id check by one entry to accept `reply_compose` writing `REPLY_VERDICT`. (§6) |
| `frontend/src/lib/pipeline/flowGraph.ts` | (optional, display) add a reply flow section so the dashboard lights reply runs. (§8) |

### REUSED (verbatim, no edits — this is the proof of separability)

| File / symbol | What the reply pipeline reuses unchanged |
|---|---|
| `app/pipeline/spec/compiler.py` `compile_spec` (doc 05) | Lowers the reply spec → `tuple[Step,...]` identically. |
| `app/pipeline/spec/validator.py` `validate_spec` (doc 05) | Validates the reply spec; R6/R7 adapted by terminal artifact (§7). |
| `app/pipeline/_runbook_engine.py` `run_steps` + invariant wrappers (doc 07) | Walks the reply graph; cost meter + guardian wrap every reply leaf. |
| `app/pipeline/events/step_trace.py` `StepTraceSink` (doc 08) | Full-fidelity per-step reply trace, NATS-independent. |
| `app/pipeline/tools/data/account_profile.py` | `data.account_profile` — same bundle load. |
| `app/pipeline/tools/deterministic/reference_rank.py` | `deterministic.reference_rank` — ranks mentions (§1 Decision Defense). |
| `app/services/pipeline_spec_repository.py` (doc 04) | `load` (kind-namespaced) / `save` / `promote_challenger` — reply specs version + promote on the SAME path. (The reply runner uses `load`, not `load_or_default` — no reply baseline; §5.1.) |
| `app/agents/safety_guardian.py` `evaluate` / `is_niche_mismatch_reject` | Guardian + niche-mismatch logic, called inside `reply_compose` unchanged. |
| `app/interval/compose_timeline_post.py` `compose_formatted_post` | Reused by `reply_compose` for the actual text generation (§4.3). |

> **`MENTIONS_RANKED` reuse note:** `reference_rank` writes to whatever `store_key` resolves to (`artifact_key_for_ctx_key(store_key)`, verified). To reuse it for mentions we need a `MENTIONS_RANKED` artifact key whose ctx-key string the wrapper passes as `store_key="mentions_ranked"`. That is the one ranking-output key we add; the ranker code is untouched.

---

## 4. The new tools, models, and platform I/O (exact, verified)

### 4.1 Platform I/O: the two additive X-client changes

Both are **purely additive** and default to today's behavior.

**(a) Reply-target on create (one optional kwarg, threaded through 4 layers).**

```python
# app/social/protocol.py — create_post gains an optional reply target
def create_post(self, text: str, *, in_reply_to: str | None = None) -> CreatedPost: ...

# app/social/implementations/x_client.py:555 — pass it ONLY when set (no behavior change otherwise)
def create_post(self, text: str, *, in_reply_to: str | None = None) -> CreatedPost:
    ua = self._user_auth
    kwargs: dict[str, Any] = {"text": text, "user_auth": ua}
    if in_reply_to:
        kwargs["in_reply_to_tweet_id"] = in_reply_to     # Tweepy create_tweet supports this
    resp = self._execute_with_backoff(lambda: self._v2.create_tweet(**kwargs))
    ...  # unchanged: id extraction + CreatedPost(id=tid, text=text)

# app/social/service.py:69 — forward it
def create_post(self, platform, creds, text, *, in_reply_to: str | None = None) -> CreatedPost:
    return self._client(platform, creds).create_post(text, in_reply_to=in_reply_to)

# app/services/twitter_service.py:147 — surface it
def post_tweet(self, account_id: str, text: str, *, in_reply_to: str | None = None) -> dict:
    acc = self._repo.load(account_id)
    if acc is None:
        raise ValueError(f"Unknown account_id={account_id}")
    created = self._call_with_auth_retry(
        acc, lambda c: self._social.create_post(SocialPlatform.X, c, text, in_reply_to=in_reply_to)
    )
    return {"id": created.id, "text": created.text or text}
```

> Every existing `post_tweet(account_id, text)` call (the post path, `post_tick.py:36`) keeps working: `in_reply_to` defaults `None`, so `create_tweet(text=...)` is called exactly as today.

**(b) Mentions read (new method, mirrors `search_tweets` shape).** Tweepy exposes `get_users_mentions(id, ...)` returning the account's mentions timeline. Add a `get_mentions` to the client/service/`TwitterService` that returns the same **row-dict** shape `search_recent_tweets` returns (so `reference_rank` consumes it without adaptation):

```python
# app/services/twitter_service.py — new read, same auth-retry plumbing as search_tweets (lines 213-239)
def get_mentions(self, account_id: str, *, max_results: int | None = None) -> list[dict]:
    acc = self._repo.load(account_id)
    if acc is None:
        raise ValueError(f"Unknown account_id={account_id}")
    cap = max_results if max_results is not None else settings.reply_mentions_max_results
    return self._call_with_auth_retry(
        acc, lambda c: self._social.get_mentions(SocialPlatform.X, c, max_results=cap)
    )
```

The `SocialMediaService.get_mentions` and `XTwitterClient.get_mentions` follow the exact pattern of `search_recent_tweets` (`service.py:77-92`, `protocol.py:51-60`) and the existing `_tweet_object_to_post_data` / row-mapping the client already uses for search results — each mention becomes a row dict carrying `tweet_id`/`text`/`author_id`/engagement counts plus the **author handle** (needed to @-mention in the reply).

> **Decision Defense — why a dedicated `get_mentions`, not "search for @handle".** Recent-search for `@handle` is rate-limited, returns non-mentions (quotes of the handle), and misses replies to the account's own tweets. The mentions timeline endpoint is the canonical, lower-cost source and is exactly what "reply to people talking to us" means. One new read method is the honest, minimal cost.

### 4.2 `mentions_fetch` (data tool)

Mirrors `own_posts_fetch.py` / `search_fetch.py` exactly (verified shapes). The live service object (`twitter`) is engine-injected; `max_results` is the one proposable literal config.

```python
"""Fetch recent X mentions of the account; write the MENTIONS artifact."""
from __future__ import annotations

from app.pipeline.types.artifacts import ArtifactKey, MentionsPayload
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.twitter_service import TwitterService

TOOL_ID = "data.mentions_fetch"
TOOL_KIND = "data"
TOOL_SOURCE = "x_mentions"
TOOL_PURPOSE = "Acquire recent mentions of the account from X for reply candidacy"
TOOL_WRITES = (ArtifactKey.MENTIONS,)
OUTPUT_MODEL = MentionsPayload

def run(
    ctx: TickRunContext,
    *,
    twitter: TwitterService,                 # [I] engine-injected (in ENGINE_INJECTED_DEPS, doc 03)
    account_id: str | None = None,
    max_results: int | None = None,          # [C] literal, proposable
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    rows = twitter.get_mentions(aid, max_results=max_results)
    payload = {"account_id": aid, "mentions": rows}
    ctx.set_artifact(ArtifactKey.MENTIONS, payload)
    return StepResult(ok=True, payload={"mention_count": len(rows)})
```

> **Catalog note (doc 03):** `twitter` is already in `ENGINE_INJECTED_DEPS` (verified `03-tool-catalog.md §4.3`), so the catalog classifies it `injected` automatically; `max_results` classifies `config`/`literal` (a proposable int) like `max_results_per_query`. The catalog changes are: add the module to `_TOOL_MODULES`, and add `"data.mentions_fetch" → steps.fetch_mentions` to `_TOOL_RUN` (the `fetch_mentions` wrapper, §4.6, spreads `twitter` + reads the literal `max_results` from the reserved ctx key). The compiler binds `fetch_mentions` by step id (§4.6).

### 4.3 `reply_compose` (LLM tool) — the DECIDE gate + compose loop in one coarse tool

This is the reply analogue of `compose_until_safe` (doc 06 §5.1). It carries TWO responsibilities, both irreducibly imperative, so they live inside ONE tool: (1) the **`reply | skip` DECIDE gate** — most mentions are not worth answering; (2) the **compose→guardian→regenerate loop** for the chosen mention. It reuses `compose_formatted_post` for the text and `guardian.evaluate` for safety, exactly as the post tool does.

> **Config-binding (canonical, doc 05 §6.2) — `reply_compose` takes only `(ctx, deps)`; its ONE proposable knob `min_mention_score` arrives via the reserved ctx-data key, NOT a `config=` kwarg.** Unlike the post ACT tools (`compose_until_safe`/`publish_post`), which have *zero* proposable config, `reply_compose` has exactly one literal knob. Doc 05's config-binding does not put a `config` kwarg on any tool `run()`; instead the compiler stashes the step's `config` dict on `ctx.data["_step_config:llm.reply_compose"]` for the wrapper's duration (doc 05 §6.2), and a thin `reply_compose_step` wrapper (added to `services/steps.py` alongside `compose_step`/`publish_step`, mirror doc 06 §7.2) reads it and forwards `(ctx, deps)`. So `reply_compose.run(ctx, deps)` reads `min_mention_score` from `ctx.data.get("_step_config:llm.reply_compose", {})` — exactly how `rank_external_references` reads `top_n` from `ctx.data.get("_step_config:deterministic.reference_rank", {})` (doc 05 §6.2). This keeps the coarse-tool signature `(ctx, deps)` uniform and makes `min_mention_score` a real, validator-graded `literal` config key (doc 03 surfaces it from the `_cfg`-read default; doc 05 R2 type-checks it as `float`).

```python
"""Coarse reply tool: DECIDE (reply|skip) then compose a guardian-safe reply to the
top-ranked mention. Writes REPLY_VERDICT always; REPLY_DRAFT only when replying."""
from __future__ import annotations

from app.agents.safety_guardian import is_niche_mismatch_reject
from app.interval.compose_timeline_post import compose_formatted_post
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.reply_compose"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Decide whether to reply to a ranked mention, then compose a guardian-safe reply"
TOOL_WRITES = (ArtifactKey.REPLY_DRAFT, ArtifactKey.REPLY_VERDICT)

def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    cfg = ctx.data.get("_step_config:llm.reply_compose", {})    # set by the wrapper (doc 05 §6.2)
    min_score = float(cfg.get("min_mention_score", 0.0))   # [C] DECIDE threshold (proposable literal)
    live = deps.live                                       # ActLive side-channel (doc 06 §4.2)
    max_rounds = max(1, int(live.max_regeneration_rounds)) # on ActLive, NOT deps (doc 06 §4.1/4.2)
    guardian = live.guardian                               # on ActLive, NOT deps (doc 06 §4.1/4.2)
    account = live.account                                 # ActLive carries the soul (doc 06 §4.2)

    ranked = ctx.get_artifact(ArtifactKey.MENTIONS_RANKED)
    candidates = list(getattr(ranked, "ranked", None) or [])

    # ── DECIDE: pick the first mention worth answering, or skip ──────────────
    winner = next((m for m in candidates if _mention_score(m) >= min_score), None)
    if winner is None:
        ctx.set_artifact(ArtifactKey.REPLY_VERDICT,
                         {"decision": "skip", "reason": "no_mention_above_threshold"})
        return StepResult(ok=True, skipped=True, skip_reason="no_mention_above_threshold")

    # ── ACT-compose: regenerate-with-guardian-feedback (same loop as compose_until_safe) ──
    target_tweet_id = _mention_tweet_id(winner)
    target_handle = _mention_author_handle(winner)
    reply_context = _format_mention_for_reply(winner)     # the mention text → compose context
    selected_body: str | None = None
    selected_round = 0
    last_reject: str | None = None
    candidate_reject: str | None = None
    for reg_round in range(max_rounds):
        body = compose_formatted_post(
            _mention_as_winner(winner),                    # adapt the mention row to the compose input
            account.category,
            account_posting_prompt=(account.posting_prompt or "").strip(),
            account_personality=(account.personality or "").strip(),
            contrast_patterns=list(account.contrast_patterns or []),
            punctuation_rules=list(account.punctuation_rules or []),
            reference_context_block=reply_context,
            regeneration_round=reg_round,
            safety_reject_reason=candidate_reject if reg_round > 0 else None,
        )
        approved, reject = guardian.evaluate(body, niche=account.category)
        if approved:
            selected_body, selected_round = body, reg_round
            break
        candidate_reject = reject or "safety_rejected"
        if is_niche_mismatch_reject(candidate_reject):
            last_reject = candidate_reject
            break

    if selected_body is None:
        ctx.set_artifact(ArtifactKey.REPLY_VERDICT,
                         {"decision": "skip", "reason": last_reject or "all_reply_attempts_failed"})
        return StepResult(ok=True, skipped=True, skip_reason=last_reject or "all_reply_attempts_failed")

    ctx.set_artifact(ArtifactKey.REPLY_DRAFT, {
        "body": selected_body,
        "in_reply_to_tweet_id": target_tweet_id,
        "target_author_handle": target_handle,
        "regeneration_round": selected_round,
    })
    ctx.set_artifact(ArtifactKey.REPLY_VERDICT,
                     {"decision": "reply", "approved": True, "in_reply_to_tweet_id": target_tweet_id})
    return StepResult(ok=True, payload={"in_reply_to_tweet_id": target_tweet_id})
```

The helper functions (`_mention_score`, `_mention_tweet_id`, `_mention_author_handle`, `_format_mention_for_reply`, `_mention_as_winner`) are thin readers over the mention row dict produced by `mentions_fetch`; they belong in this module. `_mention_as_winner` adapts the row to whatever `compose_formatted_post` expects as its first positional (`GatheredTweet`-shaped) — the reply context block (`reference_context_block`) is where the mention text actually steers the model.

> **Decision Defense — the DECIDE gate lives INSIDE `reply_compose`, not as its own typed step.** "Should we reply?" needs the *ranked mention list* and the *config threshold* in one place, and a `skip` decision must short-circuit the (expensive) LLM compose. A separate `decide_reply` step would have to write a "chosen mention" artifact for compose to read, splitting one cheap branch into two steps and two artifacts for zero flexibility (the builder cannot meaningfully reorder "decide" and "compose"). The elegant grain is exactly doc 06's: one coarse tool owns the irreducible branch+loop and writes the serializable verdict. `min_mention_score` is the one proposable knob the builder tunes to make the account chattier or pickier.

> **Decision Defense — reuse `compose_formatted_post` rather than a new reply composer.** The composition contract (soul fields + reference context + regen round + reject reason → a safe ≤280-char body, with length budget + voice polish handled internally, verified `compose_timeline_post.py:269-347`) is identical for a reply; only the *context block* differs (a mention instead of a trending reference). Reusing it means replies inherit voice polish, length budgeting, and the soul automatically, and a future soul/voice change improves replies for free. A bespoke reply composer would fork that logic and drift. The reply-specific framing ("you are replying to @X who said …") is supplied via `reference_context_block`, the existing seam.

### 4.4 `reply_publish` (data tool) + `finalize_reply`

```python
"""Coarse reply-publish tool: publish the drafted reply in-reply-to the mention,
idempotently, via finalize_reply. Reads REPLY_DRAFT + REPLY_VERDICT; writes REPLY_RESULT."""
from __future__ import annotations

from app.interval.orchestration.reply_tick import finalize_reply
from app.models.tracked_post import PostCreationMetrics
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "data.reply_publish"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Publish the approved reply in-reply-to the mention (idempotent)"
TOOL_READS = (ArtifactKey.REPLY_DRAFT, ArtifactKey.REPLY_VERDICT)
TOOL_WRITES = (ArtifactKey.REPLY_RESULT,)

_POSTED: dict[tuple[str, str], str] = {}     # (run_id, in_reply_to_tweet_id) -> reply tweet id

def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    account = live.account
    verdict = ctx.get_artifact(ArtifactKey.REPLY_VERDICT)
    draft = ctx.get_artifact(ArtifactKey.REPLY_DRAFT)

    if verdict is None or getattr(verdict, "decision", None) != "reply" or draft is None:
        reason = getattr(verdict, "reason", None) or "no_reply_decision"
        ctx.set_artifact(ArtifactKey.REPLY_RESULT,
                         {"account_id": account.account_id, "posted": False, "skipped_reason": reason})
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    target = draft.in_reply_to_tweet_id
    ledger_key = (live.run_id, target)
    if ledger_key in _POSTED:                # never double-reply on a same-run retry
        ctx.set_artifact(ArtifactKey.REPLY_RESULT, {
            "account_id": account.account_id, "tweet_id": _POSTED[ledger_key],
            "in_reply_to_tweet_id": target, "posted": True, "note": "idempotent_replay"})
        return StepResult(ok=True, payload={"idempotent_replay": True})

    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        regeneration_round=draft.regeneration_round,
        # The mention this reply answered — reused as the replied-mention exclude key so
        # rank_mentions never re-surfaces it (§4.6 _replied_mention_exclude_set).
        source_reference_tweet_id=target,
        voice_version_hash=account.voice_version_hash,
        voice_version_seq=account.voice_version_seq,
        voice_version_label=account.voice_version_label,
        # Attribution join: set EXACTLY as publish_post does (doc 07 §7) — run_id from the
        # ActLive run id, pipeline_hash from the LOADED reply spec's version_hash (NOT an
        # account accessor — none exists; it is on live.pipeline_hash, threaded by the reply
        # runner from load(aid, "champion", kind="reply").version_hash — §6). HARD PREREQ: the
        # run_id/pipeline_hash fields on PostCreationMetrics are added by doc 02 (tracked_post.py
        # :10-25 has NEITHER today); since doc 12 ships only after core docs 03-08 (which include
        # 02), the fields exist by the time this runs. If 02 has not merged, these two kwargs
        # raise (extra field) — do not implement reply_publish before doc 02's field-add.
        run_id=live.run_id,
        pipeline_hash=live.pipeline_hash,
    )
    result = finalize_reply(
        live.tick_ctx, account, draft.body,
        in_reply_to_tweet_id=target,
        target_author_handle=draft.target_author_handle,
        creation_metrics=creation_metrics,
    )
    tweet_id = (result.get("tweet") or {}).get("id") if isinstance(result, dict) else None
    if tweet_id and "error" not in result:
        _POSTED[ledger_key] = tweet_id
    ctx.set_artifact(ArtifactKey.REPLY_RESULT, {
        "account_id": account.account_id, "tweet_id": tweet_id,
        "in_reply_to_tweet_id": target, "posted": "error" not in result,
        "note": result.get("note")})
    if "error" in result:
        return StepResult(ok=False, skip_reason=str(result.get("error")), payload=result)
    return StepResult(ok=True, payload=result)
```

`finalize_reply` (`app/interval/orchestration/reply_tick.py`) is the reply analogue of `finalize_post` — **deliberately smaller** (it omits the slot/posts_total/copied-reference/snapshot mutations §2.2 flagged as post-only):

```python
"""Publish + persist a reply. Reply analogue of finalize_post, WITHOUT the
interval-slot / posts_total / copied-reference / snapshot mutations."""
from __future__ import annotations

import logging
from typing import Any

from app.interval.context import TickContext
from app.models.account import AccountDocument
from app.models.tracked_post import PostCreationMetrics
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)

def finalize_reply(
    ctx: TickContext,
    account: AccountDocument,
    body: str,
    *,
    in_reply_to_tweet_id: str,
    target_author_handle: str | None = None,
    creation_metrics: PostCreationMetrics | None = None,
) -> dict[str, Any]:
    outcomes = PipelineOutcomeRepository()
    try:
        tw_result = ctx.twitter.post_tweet(account.account_id, body, in_reply_to=in_reply_to_tweet_id)
    except Exception as exc:
        logger.warning("reply failed for %s: %s", account.account_id, exc)
        outcomes.append(account_id=account.account_id, phase="finalize_reply",
                        status="error", reason="reply_failed", details={"error": str(exc)})
        return {"account_id": account.account_id, "error": str(exc)}

    reply_id = str(tw_result.get("id") or "")
    if ctx.post_registry:
        try:
            ctx.post_registry.record_post(
                account.account_id, reply_id, ctx.now_iso,
                creation_metrics=creation_metrics,
            )
        except Exception as exc:
            logger.warning("reply registry record failed: %s", exc)
    outcomes.append(account_id=account.account_id, phase="finalize_reply", status="ok")
    return {"account_id": account.account_id,
            "tweet": tw_result, "in_reply_to_tweet_id": in_reply_to_tweet_id}
```

> **Decision Defense — a separate `finalize_reply`, not a flag on `finalize_post`.** `finalize_post` does six post-specific mutations (verified `post_tick.py:50-85`); guarding each behind an `is_reply` flag would litter the hot post path with branches and risk a reply silently consuming the interval slot. A 25-line `finalize_reply` that does *only* publish + registry-record is simpler, safer, and impossible to confuse with the post path. This is the surgical, simplicity-first choice CLAUDE.md asks for. Replies DO appear in the tracked-post registry (so engagement jobs poll them and reward §doc-01 measures them) — that reuse is intentional and free.

### 4.5 Artifacts (`app/pipeline/types/artifacts.py`)

Add five keys + models + `ARTIFACTS` entries, in the same style as the existing eight (and doc 06's three ACT keys):

```python
class ArtifactKey(StrEnum):
    ...                              # existing 8 + doc-06's COMPOSED_POST/SAFETY_VERDICT/PUBLISHED_POST
    # ── Reply pipeline (this doc) ──────────────────────────────────────
    MENTIONS = "mentions"
    MENTIONS_RANKED = "mentions_ranked"
    REPLY_DRAFT = "reply_draft"
    REPLY_VERDICT = "reply_verdict"
    REPLY_RESULT = "reply_result"


class MentionsPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    account_id: str
    mentions: list[dict[str, Any]] = Field(default_factory=list)   # tweet-row dicts (rankable)


class ReplyDraft(BaseModel):
    model_config = ConfigDict(extra="allow")
    body: str
    in_reply_to_tweet_id: str
    target_author_handle: str | None = None
    regeneration_round: int = 0


class ReplyVerdict(BaseModel):
    decision: Literal["reply", "skip"]
    approved: bool = False
    in_reply_to_tweet_id: str | None = None
    reason: str | None = None


class ReplyResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    account_id: str
    tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    posted: bool = False
    skipped_reason: str | None = None
    note: str | None = None
```

`MENTIONS_RANKED` registers `RankedReferencesPayload` (REUSED — the ranker already writes that shape; do NOT add a new model for it). The other four register their new models. Append these five entries to the `ARTIFACTS` dict (after the doc-06 ACT entries), each following the existing `ArtifactDef(key, Model, "purpose", "producer")` pattern (verified `artifacts.py:127-176`):

```python
    ArtifactKey.MENTIONS: ArtifactDef(
        ArtifactKey.MENTIONS, MentionsPayload,
        "Recent mentions of the account for reply candidacy", "steps.fetch_mentions"),
    ArtifactKey.MENTIONS_RANKED: ArtifactDef(
        ArtifactKey.MENTIONS_RANKED, RankedReferencesPayload,   # REUSED model
        "Top mentions ranked by engagement", "steps.rank_mentions"),
    ArtifactKey.REPLY_DRAFT: ArtifactDef(
        ArtifactKey.REPLY_DRAFT, ReplyDraft,
        "Composed reply body + target mention", "steps.reply_compose_step"),
    ArtifactKey.REPLY_VERDICT: ArtifactDef(
        ArtifactKey.REPLY_VERDICT, ReplyVerdict,
        "Reply|skip decision + guardian outcome", "steps.reply_compose_step"),
    ArtifactKey.REPLY_RESULT: ArtifactDef(
        ArtifactKey.REPLY_RESULT, ReplyResult,
        "X reply publish + finalize result", "steps.reply_publish_step"),
```

> `MENTIONS_RANKED`'s ctx-key string `"mentions_ranked"` is registered into `ArtifactKey`, so `ARTIFACT_KEY_BY_CTX_KEY` (`artifacts.py:179`, built `{k.value: k for k in ArtifactKey}`) resolves it automatically — that is what makes `reference_rank.run(..., store_key="mentions_ranked")` (called by the `rank_mentions` wrapper, §4.6) write to `MENTIONS_RANKED` rather than raise `Unknown ranked artifact store_key` (`reference_rank.py:38`). No edit to `artifact_key_for_ctx_key` is needed.

### 4.6 The `services/steps.py` wrappers (the wired-config + tool-binding seam)

Three thin wrappers go into `services/steps.py` (the house pattern: "the real wiring lives in `services/steps.py` wrappers, not the tools"). The compiler binds each by **step id** (doc 05 §6.0 `_WRAPPER_BY_STEP_ID`), exactly as it binds the post steps. These wrappers are where the `config_origin=="wired"` values (`store_key`, `rows`, `exclude_ids`) are supplied — never from spec config.

```python
# app/pipeline/services/steps.py — ADD these four wrappers.

def fetch_mentions(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Spread the injected `twitter` dep + the literal `max_results` config into mentions_fetch.
    Mirror of load_account_bundle (steps.py:38): the wrapper supplies engine deps; the tool
    declares them as kwargs. max_results reaches the tool via the reserved ctx-config key."""
    from app.pipeline.tools.data import mentions_fetch
    cfg = ctx.data.get("_step_config:data.mentions_fetch", {})   # literal max_results (doc 05 §6.2)
    return mentions_fetch.run(ctx, twitter=deps.twitter, max_results=cfg.get("max_results"))


def rank_mentions(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank the MENTIONS pool. Reuses deterministic.reference_rank (the TOOL); supplies the
    WIRED store_key + rows + replied-exclude (none of which are spec config). Mirror of
    rank_external_references (steps.py:123) — same tool, mention-specific wiring."""
    from app.pipeline.tools.deterministic import reference_rank
    mentions_raw = ctx.get(ArtifactKey.MENTIONS.value) or {}
    payload = mentions_raw if isinstance(mentions_raw, dict) else {}
    rows = list(payload.get("mentions") or [])
    if not rows:
        ctx.set_artifact(ArtifactKey.MENTIONS_RANKED, {"ranked": [], "winner": None})
        return StepResult(ok=True, skipped=True, skip_reason="no_mentions")
    cfg = ctx.data.get("_step_config:deterministic.reference_rank", {})   # literal top_n (doc 05 §6.2)
    return reference_rank.run(
        ctx,
        rows=rows,
        top_n=int(cfg.get("top_n", MIN_TOP_N)),
        exclude_ids=_replied_mention_exclude_set(ctx.account_id, deps),   # WIRED — replied-mention ids
        store_key=ArtifactKey.MENTIONS_RANKED.value,                      # WIRED — never spec config
    )


def reply_compose_step(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    from app.pipeline.tools.llm import reply_compose
    return reply_compose.run(ctx, deps)


def reply_publish_step(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    from app.pipeline.tools.data import reply_publish
    return reply_publish.run(ctx, deps)
```

> **`_replied_mention_exclude_set(account_id, deps)`** is the reply analogue of `copied_reference_exclude_set(account)` (`runner.py:227`): the set of mention tweet ids this account has already replied to, so `rank_mentions` never re-surfaces them. The minimal honest source is the post registry — replies are recorded via `finalize_reply` → `record_post` (§4.4), and each reply's `creation_metrics.source_reference_tweet_id` is stamped with the mention it answered (`reply_publish` sets `source_reference_tweet_id=target` on the `PostCreationMetrics` it builds, §4.4). So the exclude set is "the `source_reference_tweet_id`s of this account's reply-kind posts" — read `deps.post_registry.list_for_account(account_id)` and collect each row's `creation_metrics.source_reference_tweet_id`. Keep it a small helper in `steps.py`. (The post path's `copied_exclude` rides `deps.live.copied_exclude`; for replies it is computed here in the wrapper because `rank_mentions` runs in SENSE, before `deps.live` is read by the ACT tools — and the ranker is the only consumer.)

> **Compiler binding (doc 05 §6.0).** When doc 12 is built, add four rows to doc 05's `_WRAPPER_BY_STEP_ID` (keyed by **step id**): `"fetch_mentions" → ("data.mentions_fetch", steps.fetch_mentions)`, `"rank_mentions" → ("deterministic.reference_rank", steps.rank_mentions)`, `"reply_compose" → ("llm.reply_compose", steps.reply_compose_step)`, `"reply_publish" → ("data.reply_publish", steps.reply_publish_step)`. `rank_mentions` reuses the `deterministic.reference_rank` tool id (like the two post rankers) but binds to its own wrapper by step id — exactly the "two wrappers, one tool" precedent doc 05 §6.0 establishes. (The catalog's `_TOOL_RUN` map, doc 03 §5, keeps `deterministic.reference_rank → None` because it is shared; the per-step wrapper is resolved by the compiler from `_WRAPPER_BY_STEP_ID`, not the catalog `run_for`.)

**Definition of Done — §4**
- `python -m py_compile` clean on `artifacts.py`, the three tool files (`mentions_fetch.py`/`reply_compose.py`/`reply_publish.py`), `reply_tick.py`, and the `services/steps.py` wrapper additions.
- `len(ArtifactKey)` increased by 5; `ctx.set_artifact(ArtifactKey.REPLY_DRAFT, {"body":"hi","in_reply_to_tweet_id":"1"})` round-trips via `get_artifact`.
- `artifact_key_for_ctx_key("mentions_ranked")` resolves to `ArtifactKey.MENTIONS_RANKED` (so `reference_rank.run(..., store_key="mentions_ranked")` does not raise — verified the resolver is built from `ArtifactKey` membership, `artifacts.py:179`).
- `twitter.post_tweet(aid, "hi", in_reply_to="123")` reaches `create_tweet(..., in_reply_to_tweet_id="123")`; with no `in_reply_to` the call is byte-identical to today (a unit test asserts the kwargs dict).
- `finalize_reply` does NOT mutate `account.posts_total`, `account.last_interval_slot`, or call slot finalize/snapshot (grep the function body).
- `rank_mentions` supplies `store_key`/`rows`/`exclude_ids` itself; the reply seed (§5.3) carries NO `store_key` in any `StepSpec.config` (so doc 05 R2 `config_unknown_key` does not fire).

---

## 5. The reply PipelineSpec — its own schedule + policy

### 5.1 One spec model, the `kind` family is a repository concern (CC-12 — already in doc 04)

The reply pipeline is **the same `PipelineSpecDocument`** (doc 04) — **unchanged**. Per **CC-12**, doc 04 already added the `kind="post"` parameter to `PipelineSpecRepository.document_id`/`load`/`save` and reserved `kind="reply"` as a separate family; **the spec model itself carries NO `kind`/`pipeline_kind` field** (doc 04 §6b save note: "the family is a repository-level concern, exactly as `status` namespaces the champion/challenger"). So an account owns *two* specs — a post spec and a reply spec — versioned and promoted independently, **without any edit to `app/models/pipeline_spec.py` by this doc.** The kind lives only in the document id namespace, chosen by the repository, exactly as `status` does.

The canonical id scheme (doc 04 §3b, authoritative — do NOT re-author it here):

```python
# app/models/pipeline_spec.py — OWNED BY DOC 04 (reproduced read-only; this doc adds nothing).
@staticmethod
def document_id(account_id: str, status: str = "champion", kind: str = "post") -> str:
    # doc 04's canonical form: post keeps its byte-identical id; other kinds are
    # namespaced by PREFIX (not a suffix on the account id).
    prefix = "pipelinespecs" if kind == "post" else f"pipelinespecs-{kind}"
    suffix = "" if status == "champion" else f"-{status}"
    return f"{prefix}/{account_id}{suffix}"
```

So `document_id(aid, "champion", "reply") == "pipelinespecs-reply/{aid}"` (prefix-namespaced — NOT `pipelinespecs/{aid}-reply`), and the post id stays `pipelinespecs/{aid}` byte-for-byte. The two collections never collide.

> **Decision Defense — kind as a repository-level namespace vs a model field (settled by doc 04/CC-12).** A reply spec is structurally identical to a post spec (ordered `StepSpec`/`CompositeSpec`, champion/challenger, version stamp), so the cleanest reuse is *no model change at all*: `compile_spec`/`validate_spec`/`PipelineSpecRepository`/`bump_pipeline_version_if_needed` all already work on reply specs unchanged. Doc 04 deliberately keeps `kind` off the document (it would be a denormalized copy of the id namespace) and threads it only through the repository's `document_id`/`load`/`save` (the same place `status` lives). This doc therefore does **not** add `pipeline_kind` to the model or re-define `document_id` — that earlier draft diverged from the owner; doc 04's prefix-namespaced id is canonical. The version hash already covers only `steps` (doc 04 §5a), so two kinds with different steps naturally get different lineages.

> **Repository note (doc 04 §6b — no edit by this doc):** `PipelineSpecRepository.load` / `save` already take the `kind="post"` param threaded into `document_id`; `bump_pipeline_version_if_needed` is unchanged (it hashes `steps`). **The reply runner uses `load(aid, "champion", kind="reply")`, NOT `load_or_default` — there is deliberately NO reply baseline.** `default_pipeline_spec(account_id)` (doc 04 §3c) produces the *post* baseline (the 10-leaf SENSE+ACT post graph); falling back to it for `kind="reply"` would silently run a post pipeline on the reply cron — wrong. Replies are opt-in and seeded (`seed_reply_spec.py`, §5.3): if `load(aid, "champion", kind="reply")` returns `None` (no reply spec was seeded for this account), the reply runner skips that account with `{"skipped": "no_reply_spec"}` and never compiles/walks anything. This keeps `load_or_default`'s "no doc → POST baseline" contract intact and confines the reply path to accounts that actually have a reply spec.

### 5.2 Schedule + policy (settings, not spec-baked)

The reply *cadence* and *policy thresholds* are operational config in `Settings` (`app/core/config.py`), mirroring how posting cadence lives in settings (`post_interval_minutes`, `interval_posting_enabled`, `post_quiet_hours_*`, verified `main.py:49-130`). Adding them to settings (not the spec doc) keeps the spec a pure *behavior* description and the schedule an *ops* concern — the same split the post pipeline already has.

```python
# app/core/config.py — additive Settings fields (defaults conservative)
reply_enabled: bool = False                  # MASTER SWITCH — off by default; replies are opt-in
reply_poll_minutes: int = 30                 # how often run_reply_job fires
reply_max_per_run: int = 1                    # at most N replies per account per run (start at 1)
reply_min_mention_score: float = 0.0         # DECIDE threshold seeded into reply_compose config
reply_mentions_max_results: int = 20         # mentions_fetch page size
# reply quiet-hours REUSE the existing post_quiet_hours_* fields (no new ones).
```

> **Decision Defense — `reply_max_per_run` and `reply_min_mention_score` are policy, surfaced two ways.** The *hard cadence* (`reply_poll_minutes`) and the *master switch* (`reply_enabled`) are pure ops → settings only. `reply_min_mention_score` is *also* a spec-proposable config on the `reply_compose` step (§4.3) — the seed reads `settings.reply_min_mention_score` as the baseline, and the builder may later tune it per-account via the challenger spec. `reply_max_per_run` is enforced by the **runner loop** (§6), not the spec, because "how many replies per run" is a scheduling concern outside any single spec walk. This keeps the spec describing *one reply's behavior* and the runner owning *how many times to walk it*.

### 5.3 Seed (`scripts/seed_reply_spec.py`)

Mirror `seed_pipeline_spec.py` (doc 04 §7). Build the reply spec's `StepSpec` list directly (it is short and has no composite), and `PipelineSpecRepository().save(spec, kind="reply")` (which versions + archives a `v1` revision on the reply-namespaced path). **There is no `pipeline_kind` field to stamp on the document (CC-12) — the reply family is selected by the `kind="reply"` argument to `save`, which routes `document_id` to the `pipelinespecs-reply/{aid}` namespace:**

```python
def reply_spec(account_id: str) -> PipelineSpecDocument:
    steps = [
        StepSpec(id="load_account_bundle", tool_id="data.account_profile",
                 writes=["account_bundle"], purpose="Load profile + engagement"),
        StepSpec(id="fetch_mentions", tool_id="data.mentions_fetch",
                 reads=["account_bundle"], writes=["mentions"],
                 config={"max_results": 20}, purpose="Fetch recent mentions"),
        StepSpec(id="rank_mentions", tool_id="deterministic.reference_rank",
                 reads=["mentions"], writes=["mentions_ranked"],
                 config={"top_n": 10}, purpose="Rank mentions"),   # NO store_key — wired by the wrapper (§4.6)
        StepSpec(id="reply_compose", tool_id="llm.reply_compose",
                 reads=["mentions_ranked"], writes=["reply_draft", "reply_verdict"],
                 config={"min_mention_score": settings.reply_min_mention_score},
                 purpose="Decide + compose a safe reply"),
        StepSpec(id="reply_publish", tool_id="data.reply_publish",
                 reads=["reply_draft", "reply_verdict"], writes=["reply_result"],
                 purpose="Publish the reply (idempotent)"),
    ]
    return PipelineSpecDocument(account_id=account_id, steps=steps, status="champion")

# main(): spec = reply_spec("JohnJames_News"); PipelineSpecRepository().save(spec, kind="reply")
# The kind="reply" arg (NOT a model field) routes save → document_id(aid, "champion", "reply")
# → "pipelinespecs-reply/JohnJames_News". The post seed is untouched.
```

> **`store_key` is DELIBERATELY ABSENT from `rank_mentions` config.** Same root cause as doc 04's post seed: `store_key` is `config_origin=="wired"` (doc 03 §4.4), so doc 05 R2 (`config_unknown_key`) rejects it on `StepSpec.config`. The `rank_mentions` *wrapper* (§4.6) supplies `store_key=ArtifactKey.MENTIONS_RANKED.value` itself, exactly as `rank_external_references` hard-codes `store_key=ArtifactKey.TIMELINE_RANKED.value` (`steps.py:139`). The only literal config a rank step may carry is `top_n`. `reply_compose`'s `min_mention_score` is seeded from `settings.reply_min_mention_score` (§5.2) and reaches the tool via the reserved ctx-data key (§4.3); it IS a `literal` knob the builder may tune.
> **The reply spec is flat** (no `parallel`/`chain`) — ranking one mention list needs no parallel branch. The dotted flatten ids are the bare step ids (`fetch_mentions`, `rank_mentions`, `reply_compose`, `reply_publish`), which the frontend reply section (§8) matches.

**Definition of Done — §5**
- `PipelineSpecDocument.document_id("acct", "champion", "reply") == "pipelinespecs-reply/acct"` (prefix-namespaced per doc 04 §3b); `document_id("acct")` is unchanged (`"pipelinespecs/acct"`). The model gains NO field (CC-12).
- `seed_reply_spec.py` writes `pipelinespecs-reply/JohnJames_News` (champion) + a `v1` revision; re-running is idempotent (no spurious `v2`).
- `compile_spec(reply_spec(...), catalog=get_tool_catalog())` succeeds and `validate_spec(reply_spec(...), get_tool_catalog(), kind="reply")` returns `ok` (with the kind-parameterized R6/R7 of §7, and `rank_mentions`/`reply_*` rows added to the compiler's `_WRAPPER_BY_STEP_ID`, §4.6). The catalog is the `ToolCatalog` object from the single factory `get_tool_catalog()` (CC-1 — `build_tool_catalog`/`build_catalog` are not the validator/compiler entry point). Gated on the reply tools + the three new wrappers existing.

---

## 6. Trigger: a separate scheduler job + thin reply runner

Replies fire on their **own** cron, independent of the posting tick.

```python
# app/main.py — inside _build_scheduler(), additive (mirrors the engagement_poll block 60-68)
if settings.reply_enabled:
    sched.add_job(
        run_reply_job,
        IntervalTrigger(minutes=max(1, int(settings.reply_poll_minutes)), timezone=tz),
        id="reply_poll", replace_existing=True,
        misfire_grace_time=misfire, coalesce=True, max_instances=1,
    )
```

```python
# app/jobs/reply_job.py — entrypoint (mirror of run_interval_job + Orchestrator.run_tick;
# builds the SAME live-service container, then loops the SAME active accounts).
from app.interval.orchestration.posting_hours import is_post_quiet_hours  # verified jobs/interval_job.py:5
from app.interval.orchestration.pre_tick import phase1_global_setup       # verified pre_tick.py:9 (loads ctx.accounts)
from app.interval.runner import build_tick_context                        # verified runner.py:60
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.tick_data_service import TickDataService
from app.services.twitter_service import TwitterService
from app.agents.safety_guardian import SafetyGuardian

def run_reply_job() -> dict:
    if not settings.reply_enabled:
        return {"skipped": "reply_disabled"}
    if is_post_quiet_hours():                       # REUSE the post quiet-hours helper (verified)
        return {"skipped": "quiet_hours"}
    # Same service container Orchestrator.run_tick builds (orchestrator.py:57-72).
    repo = AccountRepository()
    twitter = TwitterService(repo)
    post_registry = TrackedPostRepository()
    pulled = PulledTweetRepository()
    tick_data = TickDataService(repo, twitter, post_registry, pulled)
    ctx = build_tick_context(
        repo=repo, twitter=twitter, guardian=SafetyGuardian(), tick_data=tick_data,
        post_registry=post_registry, mode="scheduled",
        max_regeneration_rounds=max(1, int(settings.max_regeneration_rounds)),
    )
    phase1_global_setup(ctx)                         # populates ctx.accounts (pre_tick.py:9, same as posting)
    results: list[dict] = []
    for account in ctx.accounts:                     # the SAME active accounts as the posting tick
        for _ in range(max(1, int(settings.reply_max_per_run))):
            out = run_reply_pipeline(ctx, account)   # one reply attempt (the reply driver below)
            results.append(out)
            if out.get("skipped") or out.get("error") or not out.get("tweet"):
                break                                # nothing more to reply to this account this run
    return {"results": results}
```

> **Symbol sources for the driver below (all reused, none new to this doc):** `StepTraceSink`/`set_trace_sink`/`reset_trace_sink` (doc 08); `run_events`/`emit_run_started`/`emit_run_completed`/`current_run_id`/`NatsPublishSink` (events package, reused verbatim — same imports `run_account_pipeline` uses, `runner.py:143-149`); `start` (the `TickRunContext` factory, `runbook.py:9`); `run_steps` (`_runbook_engine.py:151`); `engine_invariants`/`CostMeter` (doc 07 §3-4); `compile_spec`/`validate_spec` (doc 05); `get_tool_catalog` (the single catalog factory — CC-1; from `app.pipeline.spec.catalog`, the `ToolCatalog` object doc 05's validator/compiler accept, NOT the raw list `build_tool_catalog`); `PipelineSpecRepository`/`load(aid, "champion", kind="reply")` (doc 04 + §5.1 — `load`, not `load_or_default`); `ActLive` (doc 06 §4.2); `post_run_deps_from_tick` — **its post-doc-07 home** is `app/interval/run_deps.py` (doc 07 §5 moves it out of the deleted `reference_phase.py`), so import `from app.interval.run_deps import post_run_deps_from_tick`. `run_reply_pipeline` does NOT call `try_reserve_interval_slot`/`try_begin_post` (no slot/guard for replies — see the note after this block).

```python
# app/interval/reply_runner.py — the per-account driver (mirror of run_account_pipeline, doc 07 §2)
def run_reply_pipeline(ctx: TickContext, account: AccountDocument) -> dict[str, Any]:
    run_id = ctx.forced_run_id or uuid4().hex
    trace = StepTraceSink(run_id=run_id, account_id=account.account_id,
                          slot=ctx.slot, mode=ctx.mode, niche=account.category or "")
    token = set_trace_sink(trace)
    with run_events(run_id=run_id, account_id=account.account_id, slot=ctx.slot,
                    mode=ctx.mode, sinks=[NatsPublishSink(), trace]):
        emit_run_started(niche=account.category or "")
        status = "error"
        try:
            # load (NOT load_or_default): there is no reply baseline; skip un-seeded accounts (§5.1).
            spec = PipelineSpecRepository().load(account.account_id, "champion", kind="reply")
            if spec is None:
                return {"account_id": account.account_id, "skipped": "no_reply_spec"}
            catalog = get_tool_catalog()               # CC-1: the single factory → ToolCatalog object
            report = validate_spec(spec, catalog, kind="reply")   # kind passed in (no model field — CC-12); ValidationReport (doc 05 §5.2)
            if not report.ok:
                return {"account_id": account.account_id, "error": f"invalid_reply_spec:{report.codes()[0]}"}
            graph = compile_spec(spec, catalog=catalog)   # same catalog object (doc 05 §6)
            run_ctx = start(account.account_id, niche=account.category, mode=ctx.mode, slot=ctx.slot)
            run_ctx.run_id = run_id                     # threaded param, == current_run_id() (doc 07 §6)
            deps = post_run_deps_from_tick(ctx)         # SAME deps builder; doc 06's only extension is live
            # ActLive carries EXACTLY doc 06 §4.2 / CC-7's fields. The reply tools read guardian /
            # max_regeneration_rounds / account / run_id / pipeline_hash off live (NOT off deps —
            # there is no deps.guardian; doc 06 §4.1 reconciled the deps extension to ONLY `live`).
            # NOTE (CC-7): ActLive has NO reference_context_block/refs_payload/reference_pool fields —
            # those were removed; the POST compose tool derives them internally from SENSE artifacts.
            # Replies don't use them at all (reply_compose reads MENTIONS_RANKED). `twitter` and
            # `post_registry` ARE required ActLive fields (CC-7 names them) → pass ctx.twitter /
            # ctx.post_registry. copied_exclude is unused by replies (the rank_mentions wrapper
            # computes its own replied-mention exclude set, §4.6) → leave it at its frozenset() default.
            deps.live = ActLive(
                account=account,
                tick_ctx=ctx,
                guardian=ctx.guardian,
                twitter=ctx.twitter,                    # CC-7 — required ActLive field (== tick_ctx.twitter)
                post_registry=ctx.post_registry,        # CC-7 — required ActLive field (== tick_ctx.post_registry)
                run_id=run_id,
                pipeline_hash=spec.version_hash,        # reply spec version → creation_metrics.pipeline_hash
                max_regeneration_rounds=ctx.max_regeneration_rounds,
                bypass_post_cooldown=ctx.bypass_post_cooldown,
            )
            meter = CostMeter(run_id=run_ctx.run_id, ceiling_usd=settings.pipeline_cost_ceiling_usd)
            # engine_invariants(*, meter) — canonical signature (doc 07 §3.2); it takes NO guardian/niche
            # (the guardian runs INSIDE reply_compose; the engine wrapper only asserts the verdict artifact).
            result = run_steps(graph, run_ctx, deps,
                               wrappers=engine_invariants(meter=meter))
            out = _reply_result_from_run(run_ctx, account, result)
            status = _run_status_from_out(out)
            return out
        finally:
            duration_ms = 0
            emit_run_completed(status=status, duration_ms=duration_ms)
            trace.finalize(status=status, duration_ms=duration_ms)
            reset_trace_sink(token)
```

> **No slot/post guard for replies.** The post path's slot reservation + cooldown (`slot_claim.py`, `post_guard.py`) exist to prevent two *interval posts* in the same slot. A reply does not consume the interval slot, so it must NOT call them — `reply_runner` deliberately omits `try_reserve_interval_slot` / `try_begin_post`. The reply's own double-post protection is the `reply_publish` `(run_id, in_reply_to_tweet_id)` ledger (§4.4) plus the `exclude_ids` of already-replied mentions fed into `rank_mentions`. `max_instances=1` on the cron prevents overlapping reply runs.

> **`engine_invariants` reused verbatim:** the cost meter + guardian wrappers (doc 07 §3) wrap every reply leaf identically. Doc 07 §3.2's `guardian_wrapper` keys on the bare step id `flat.id == "compose_until_safe"` and asserts that step wrote `SAFETY_VERDICT`; for the reply graph the guardian-bearing leaf is `reply_compose` writing `REPLY_VERDICT`. That is a **one-line widening** of the step-id check — `if flat.id in ("compose_until_safe", "reply_compose")` with the asserted artifact chosen by which leaf matched (`SAFETY_VERDICT` for compose, `REPLY_VERDICT` for reply). This is a step-id check, **not** an `invariant_tool`-flag check (doc 05's validator carries no such flag — §7); doc 07 owns the widening when replies are built. The cost meter needs no change — it tallies all leaves (and `reply_compose`'s internal `compose_formatted_post` + `guardian.evaluate` Claude calls accrue via the `ClaudeClient` accumulator, doc 07 §4.1, so the ceiling trips on reply LLM spend exactly as on posts).

`_reply_result_from_run` (in `reply_runner.py`) maps the terminal `REPLY_RESULT`/`REPLY_VERDICT` artifacts to the legacy dict shape `_run_status_from_out` reads (`{skipped}` | `{error}` | a success dict with `tweet`), the reply analogue of doc 07 §2.6's `_result_from_run`:

```python
def _reply_result_from_run(run_ctx, account, result) -> dict[str, Any]:
    aid = account.account_id
    if not result.ok:                                   # a SENSE step failed/skipped (e.g. no mentions)
        return {"account_id": aid, "skipped": "reply_sense_skipped"}
    verdict = run_ctx.get_artifact(ArtifactKey.REPLY_VERDICT)   # written by reply_compose on every path
    if verdict is None or verdict.decision != "reply":
        return {"account_id": aid, "skipped": (verdict.reason if verdict else None) or "no_reply_decision"}
    published = run_ctx.get_artifact(ArtifactKey.REPLY_RESULT)  # written by reply_publish
    if published is None or not published.posted:
        return {"account_id": aid, "error": (published.skipped_reason if published else None) or "reply_publish_missing"}
    return {"account_id": aid, "tweet": {"id": published.tweet_id},
            "in_reply_to_tweet_id": published.in_reply_to_tweet_id}
```

> `_run_status_from_out` (`runner.py:129-136`, reused) classifies this exactly as it does a post result: `{skipped}` → `"skipped"`, `{error}` → `"error"`, the `tweet` dict → `"ok"`. The §6 `run_reply_job` loop reads `out.get("tweet")`/`out.get("skipped")`/`out.get("error")` to decide whether to attempt another reply for the account — so the shapes line up end-to-end. (`ReplyVerdict.decision` is a required field, so `verdict.decision` is always present once the model validates.)

**Definition of Done — §6**
- With `reply_enabled=true`, the `reply_poll` job is registered and fires on `reply_poll_minutes`; with `reply_enabled=false` (default) it is absent and posting is unaffected.
- `run_reply_pipeline` walks SENSE+DECIDE+ACT in one `run_steps` call on the **reply** spec; a mention above threshold yields a reply tweet in-reply-to it; below threshold yields `{"skipped": ...}` and no X write.
- A reply run produces full-fidelity `StepOutputDocument`s (doc 08) for `fetch_mentions`/`rank_mentions`/`reply_compose`/`reply_publish` even with NATS OFF.
- The posting tick (`run_interval_job`) is byte-for-byte unchanged; turning replies on/off does not touch it.

---

## 7. Catalog + validator fit (the reply tools are honest catalog citizens)

- **Catalog (doc 03):** add `mentions_fetch`, `reply_compose`, `reply_publish` to `_TOOL_MODULES` in `catalog.py`, and add their `(tool_id → wrapper)` rows to `_TOOL_RUN` (`data.mentions_fetch → steps.fetch_mentions`; `llm.reply_compose → steps.reply_compose_step`; `data.reply_publish → steps.reply_publish_step`, §4.6). `deterministic.reference_rank` stays `→ None` in `_TOOL_RUN` (shared by post rankers + `rank_mentions`; the compiler binds `rank_mentions` per-step via `_WRAPPER_BY_STEP_ID`). `twitter` is already in `ENGINE_INJECTED_DEPS`, so `mentions_fetch`'s `twitter` classifies `injected` and its `max_results` classifies `config`/`literal` automatically. `reply_compose`/`reply_publish` take `(ctx, deps)` exactly like `compose_until_safe`/`publish_post` (no `config` kwarg — config arrives via the reserved ctx-data key, §4.3), so the catalog introspects them to `parameters=[]`/`proposable_params=[]` with no new machinery. Declare each tool's fixed I/O via the module constants the catalog reads (`TOOL_WRITES`, and `TOOL_READS` on the two ACT-shaped tools) so the catalog's `writes`/`reads` are concrete — this is what R6/R7 key off (below): `reply_compose` `TOOL_WRITES=(REPLY_DRAFT, REPLY_VERDICT)`, `reply_publish` `TOOL_READS=(REPLY_DRAFT, REPLY_VERDICT)` / `TOOL_WRITES=(REPLY_RESULT,)`.

  > **No `invariant_tool=True` marking.** Doc 05 (the validator owner) ships **no** `invariant_tool` flag and detects invariant-bearing tools by their static catalog `writes` instead (doc 05 §3.2/§4: the guardian-bearing tool is "the tool whose catalog `writes` includes the verdict key"; the publish tool is "the tool whose catalog `writes` includes the terminal key"). So there is nothing to mark — `reply_compose`/`reply_publish` are recognized purely because their `TOOL_WRITES` declare `REPLY_VERDICT`/`REPLY_RESULT`. (Doc 03's `ToolCatalogDocument` has an `invariant_tool` field, but doc 05 does not consume it; relying on it would diverge from the validator that actually grades the reply spec.)

- **Validator (doc 05):** the seven rules apply unchanged **except** the terminal/invariant checks (R6/R7), which are hard-coded against the *post* terminal artifacts (`PUBLISHED_POST`, `SAFETY_VERDICT`). For the reply spec the terminal is `REPLY_RESULT` and the guardian-bearing verdict is `REPLY_VERDICT`. **Because the spec document carries NO `kind` field (CC-12), the validator cannot read the kind off `doc` — so `validate_spec` gains a `kind: str = "post"` keyword param** (`validate_spec(doc, catalog, *, kind="post")`); the caller that knows the family (the reply runner §6, `promote_challenger`, the builder) passes `kind="reply"`. R6/R7 then index a small `kind → (verdict_key, terminal_key)` table:
  ```python
  _KIND_TERMINALS = {
      "post":  (ArtifactKey.SAFETY_VERDICT.value, ArtifactKey.PUBLISHED_POST.value),
      "reply": (ArtifactKey.REPLY_VERDICT.value,  ArtifactKey.REPLY_RESULT.value),
  }
  verdict_key, terminal_key = _KIND_TERMINALS[kind]
  ```
  R6 requires exactly one terminal leaf whose **spec-node** `writes` includes `terminal_key` (and nothing after it — `step_after_publish` framing unchanged), and R7 requires (a) at least one leaf whose **catalog tool's** `writes` includes `verdict_key` (the guardian-bearing `reply_compose`), and (b) the terminal `terminal_key` writer's **catalog tool's** `writes` statically include `terminal_key` (so the terminal is the real `reply_publish`, not a hand-rolled leaf that merely declares the write). This mirrors doc 05's exact R6-uses-spec-node-writes / R7-uses-catalog-writes split (doc 05 §5) — the only change is the artifact names come from `_KIND_TERMINALS[kind]` (the passed param) instead of being literal. A small, additive branch in `validate_spec` (plus the `kind` kwarg, default `"post"` so every existing post call site is unchanged), not a rewrite. (Owning doc: 05 takes the parameterization when replies are built; this doc specifies the exact table + rule + signature.)

> **Decision Defense — parameterize R6/R7 by kind (via catalog `writes`) rather than hardcode reply artifact names or add an `invariant_tool` flag.** The validator's job (doc 05 §4) is "the spec is shaped so the engine's non-bypassable enforcement will happen." That shape is *the same* for posts and replies — a guardian-bearing compose tool (recognized by its catalog `writes` including the verdict key) feeds a publish-bearing terminal (recognized by its catalog `writes` including the terminal key) — only the artifact names differ. A `kind`-keyed lookup of `(verdict_key, terminal_key)` is the minimal honest generalization; it keeps one validator for both pipelines, reuses doc 05's exact catalog-`writes` detection (no new `invariant_tool` machinery), and makes adding a third behavior later (e.g. quote-tweets) a one-row addition, not a new validator.

**Definition of Done — §7**
- `get_tool_catalog()` (CC-1, the single factory) returns a `ToolCatalog` that includes the 3 new tools; `reply_compose`'s catalog `writes` includes `reply_verdict` and `reply_publish`'s catalog `writes` is `[reply_result]` (concrete, from `TOOL_WRITES`); `mentions_fetch`'s `twitter` is `injected`, `max_results` is `literal`.
- `validate_spec(reply_spec, get_tool_catalog(), kind="reply")` returns `ok` for the §5.3 seed and flags `missing_publish_invariant` if the terminal `reply_result` writer's `tool_id` is swapped for a tool whose catalog `writes` does not include `reply_result` (e.g. `data.account_profile`), and `missing_safety_invariant` if no leaf's catalog `writes` includes `reply_verdict` (R7 keyed on catalog `writes`, NOT an `invariant_tool` flag).

---

## 8. Frontend (optional display)

The dashboard reuse is free: a reply run streams the same `PipelineProgressEvent`s and writes the same trace docs. To light reply nodes, add a `REPLY_FLOW` section to `frontend/src/lib/pipeline/flowGraph.ts` (the runbook header warns these ids must match `flatten_steps` output — verified `flowGraph.ts:1-19`): nodes `fetch_mentions`, `rank_mentions`, `reply_compose`, `reply_publish` (bare ids — the reply spec is flat). This is purely additive and gated on whether a reply run is being viewed; the existing post flow is untouched. **Defer unless the reply dashboard is wanted** — replies trace and persist regardless of frontend work.

---

## 9. End-to-end separability matrix (the proof)

| Concern | Post pipeline (docs 03–08) | Reply pipeline (this doc) | Shared mechanism |
|---|---|---|---|
| Spec model | `PipelineSpecDocument` @ `pipelinespecs/{aid}` | `PipelineSpecDocument` @ `pipelinespecs-reply/{aid}` | **same model (no edit)**; `kind` is a repository-id namespace, not a field (CC-12) |
| Compile | `compile_spec` | `compile_spec` | **identical**, unchanged |
| Validate | `validate_spec(doc, cat)` R1–R7 | `validate_spec(doc, cat, kind="reply")` R1–R7 (R6/R7 kind-parameterized) | **same validator**, one `kind` kwarg + one branch |
| Engine | `run_steps` + cost/guardian wrappers | `run_steps` + cost/guardian wrappers | **identical**, unchanged |
| Trace | `StepTraceSink` | `StepTraceSink` | **identical**, unchanged |
| Versioning/promote | `bump_pipeline_version_if_needed` / `promote_challenger` | same | **identical**, unchanged |
| Trigger | `run_interval_job` (interval tick) | `run_reply_job` (separate cron) | independent jobs |
| Publish | `publish_post` → `finalize_post` | `reply_publish` → `finalize_reply` | parallel, reply omits slot/posts_total |
| Genuinely new code | — | 3 tools + 4 step wrappers, 1 `finalize_reply`, 1 X read, 1 `in_reply_to` arg, 1 cron, 1 runner, 5 `ArtifactKey`s; + ~6 one-line wiring rows in compiler/validator/catalog/guardian-wrapper | the entire delta |

**The delta to add replies is: three catalog tools, four thin `services/steps.py` wrappers, one small `finalize_reply`, one additive X read (`get_mentions`), one optional `in_reply_to` kwarg, five artifact keys, one settings block, one cron job, one thin runner, and ~6 one-line wiring rows (compiler `_WRAPPER_BY_STEP_ID`, validator R6/R7 kind table, catalog `_TOOL_RUN`, guardian-wrapper step id).** Everything else — the spec lifecycle, compiler, validator, engine, invariants, trace, versioning, attribution, reward — is **reused with only those additive one-line wirings, no behavior change to posts.** That is the architectural promise the Interpreter was built to keep, and this doc is its receipt.

---

## 10. Definition of Done (whole slice, when/if built)

- `python -m py_compile` clean across all new/changed backend files.
- `pytest` green, including: an `in_reply_to=None` call to `create_post` is byte-identical to today; `finalize_reply` performs no post-only mutations; `reply_compose` skips below threshold and composes+guardian-loops above it; `reply_publish` never double-replies on a same-run replay.
- Seed writes a champion reply spec to `pipelinespecs-reply/{aid}` via `save(spec, kind="reply")` (no `pipeline_kind` model field — CC-12); `compile_spec`+`validate_spec(..., kind="reply")` accept it.
- With `reply_enabled=true` and a real mention, a reply run posts in-reply-to the mention, records a `TrackedPostDocument`, and writes full-fidelity step trace (NATS OFF). With `reply_enabled=false`, the system behaves exactly as the post-only Interpreter.
- `docker compose up -d --build` healthy; the posting tick is provably unaffected (a post force-run still produces the identical result it did before this doc).

---

## 11. Cross-references (shared types owned elsewhere)

- **doc 03 — tool catalog:** owns `_TOOL_MODULES` + `_TOOL_RUN` + `ENGINE_INJECTED_DEPS` (`twitter` already present); add the 3 reply tools to `_TOOL_MODULES` and their wrappers to `_TOOL_RUN` (§7). Note (CC-2): there is **no** `invariant_tool`/`TOOL_INVARIANT` field — doc 05's validator detects the reply terminal/guardian purely from catalog `writes` (R6/R7, §7).
- **doc 04 — pipeline spec + versioning:** owns `PipelineSpecDocument` + `PipelineSpecRepository` + versioning. Per **CC-12**, doc 04's canonical `document_id`/`load`/`save` **already** take a `kind="post"` param (the reply family is reserved there), and the model carries **no** `kind`/`pipeline_kind` field — so this doc adds **nothing** to `app/models/pipeline_spec.py` (§5.1). Doc 04's `document_id` namespaces by PREFIX (`pipelinespecs-reply/{aid}` for `kind="reply"`), keeping the post id byte-identical (`pipelinespecs/{aid}`). The reply runner reads via `load(aid, "champion", kind="reply")` (not `load_or_default` — no reply baseline); the seed writes via `save(spec, kind="reply")`.
- **doc 05 — validator + compiler:** owns `validate_spec(doc, catalog)` (takes the `ToolCatalog` object from `get_tool_catalog()` — CC-1, returns a `ValidationReport`) + `compile_spec(doc, *, catalog=None)`. This doc specifies the kind-parameterized R6/R7 (detected by catalog `writes`, NOT an `invariant_tool` flag — §7) and requires the compiler's `_WRAPPER_BY_STEP_ID` (doc 05 §6.0) gain three rows for `rank_mentions`/`reply_compose`/`reply_publish` (§4.6). The lowering path itself is unchanged (the flat reply spec uses the same `chain`/`parallel`-free leaf path).
- **doc 06 — ACT path as typed steps:** owns the `ActLive` dataclass (carries `account`/`tick_ctx`/`guardian`/`run_id`/`pipeline_hash`/`max_regeneration_rounds`/`bypass_post_cooldown` + the post-only reference fields) and the **single** `PostRunDeps` extension `live: ActLive` (NOT `deps.guardian`/`deps.max_regeneration_rounds` directly — reconciled in doc 06 §4.1); `compose_until_safe`, `publish_post`; and the idempotency-ledger pattern this doc mirrors for `reply_publish` (keyed `(run_id, in_reply_to_tweet_id)` instead of `(run_id, account_id)`). The reply tools read `deps.live.guardian` / `deps.live.max_regeneration_rounds` / `deps.live.account`.
- **doc 07 — interpreter wiring:** owns `engine_invariants` + `CostMeter` + `run_steps` wrappers (reused verbatim) + the `ClaudeClient` per-run cost accumulator (so the cost ceiling trips on reply LLM spend automatically). Doc 07 §3.2's `guardian_wrapper` keys on `flat.id == "compose_until_safe"`; the one-line widening to `flat.id in ("compose_until_safe", "reply_compose")` (asserting `REPLY_VERDICT` for the reply leaf) is doc 07's edit when replies are built (§6).
- **doc 08 — step trace:** owns `StepTraceSink` + `StepOutputDocument` (reused verbatim; reply steps trace automatically through the same `_run_step_with_progress` path).
- **doc 01 — reward / doc 02 — attribution:** reply tweets land in `TrackedPostDocument` via `finalize_reply` → `record_post`, so engagement jobs poll them and reward measures them with **zero** extra work; when `run_id`/`pipeline_hash` land on `PostCreationMetrics`, `reply_publish` stamps them exactly as `publish_post` does.

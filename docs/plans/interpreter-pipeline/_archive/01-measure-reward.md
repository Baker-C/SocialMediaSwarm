# 01 — MEASURE: Normalized Reward Function

> **Status:** Ready to implement. Authored cold against the live code (June 2026); pick up from this folder.
> **Phase:** MEASURE — the first of the Interpreter loop (MEASURE → LEARN → BUILD → RUN). This doc owns the *reward signal* only.
> **Scope:** Backend only. One greenfield module (`app/reward/reward_function.py`) + a small extension to `app/jobs/metrics_job.py` + one new field on `AccountMetricsDocument`. No frontend, no X-API changes, no new polling.
> **Target project:** `SocialMediaAutonomousAgents/backend/` (FastAPI + RavenDB + APScheduler).
> **DB reality:** One account today — `JohnJames_News`. Reward is computed per-post and aggregated per-account; an account with zero polled posts simply yields `None`.

---

## 1. Why this exists (and what it is NOT)

The Interpreter rewrites each account's posting pipeline based on *what worked*. "What worked" must be a **single, comparable, normalized number per post** — otherwise LEARN (doc `09` — Champion/Challenger Evaluation + Self-Rewrite) is comparing raw like-counts across posts with wildly different reach, which rewards luck (a post that happened to be shown to 50k people) over skill (a post that converted the people it reached).

This doc defines that number: **`post_reward ∈ [0, 1]`**, a reach-normalized composite of three already-measured signals. It is computed **passively, from snapshot rows the engagement jobs already poll** — it adds **zero** X-API calls.

**What this is NOT (explicit non-goals, do not build):**
- **NOT a new polling job.** The prior incident (see `MEMORY.md → pipeline-search-and-metrics`) was per-tick metrics polling exploding X-API usage. Reward is pure arithmetic over rows already in RavenDB. It rides the existing `run_metrics_job` (hourly cron, **zero** X calls). See §6 Decision Defense.
- **NOT attribution.** Linking a reward back to the `run_id` / `pipeline_hash` that produced the post is a *separate* missing-join (doc `02` — Outcome Ledger + Attribution, which adds the optional `run_id`/`pipeline_hash` fields to `PostCreationMetrics`, `models/tracked_post.py:10-25`). This doc computes reward keyed by `tweet_id`; LEARN (doc `09`) performs the join. We only consume `voice_version_hash` (already stamped, `tracked_post.py:22`) opportunistically for grouping.
- **NOT LEARN.** Selecting champion/challenger specs, A/B comparison, and promotion live in doc `09` — Champion/Challenger Evaluation + Self-Rewrite. This doc stops at "every post has a reward, and the account has an average."

---

## 2. The reward, precisely

`post_reward` is a weighted sum of three sub-scores, each already in `[0, 1]`:

```
post_reward = w_eng · R_engagement      (reach-normalized engagement rate, squashed)
            + w_vel · R_velocity        (early-engagement velocity, squashed)
            + w_rep · R_reply           (reply quality = reply share of engagement)

with   w_eng = 0.60,  w_vel = 0.25,  w_rep = 0.15      (sum = 1.0)
```

Every sub-score is in `[0, 1]`, the weights sum to 1, so `post_reward ∈ [0, 1]`. Higher is better.

### 2.1 `R_engagement` — reach-normalized engagement rate (weight 0.60)

The core signal. `engagement_rate` is **already computed and stored** on every snapshot/TrackedPost as `(likes + replies + retweets + quotes) / impressions` (`app/metrics/derived.py:17-36`, function `compute_rates`). It is reach-normalized **by construction** — dividing by impressions removes the "got lucky with reach" confound.

Raw engagement rates are tiny and long-tailed (a great X post is ~3–6%; a viral one ~10%+). To make the sub-score occupy a useful `[0, 1]` range and stop saturating, squash with a saturating curve anchored so that a "good" rate (`ENG_RATE_REFERENCE = 0.05`, i.e. 5%) maps to ~0.5:

```
R_engagement = saturate(engagement_rate, ref = ENG_RATE_REFERENCE)
             = e / (e + ref)                       # e = engagement_rate, ref = 0.05
```

- `e = 0`    → `R = 0.0`
- `e = ref`  → `R = 0.5`
- `e = 0.10` → `R = 0.667`
- `e → ∞`    → `R → 1.0` (asymptote; never reaches 1)

This `x / (x + ref)` form is monotonic, bounded, parameter-light (one constant), and needs no per-account calibration. **Defaults chosen** rather than fit-to-data because we have one account and ~tens of posts; a learned normalizer would overfit. Revisit when N(posts) ≫ 100.

### 2.2 `R_velocity` — early-engagement velocity (weight 0.25)

Rewards posts that **earned engagement fast**, not just eventually. Velocity is **already computed** by `compute_velocity` (`derived.py:39-51`) as `Δengagement / Δimpressions` between two consecutive snapshots, and stored as `engagement_velocity` on snapshots and on the TrackedPost row (the field is declared at `tracked_post.py:49`; `post_registry.update_metrics` writes it when present, `post_registry.py:179-180`). It captures "how efficiently did newly-reached impressions convert" early in the post's life (the `early_engagement_job`, every 15 min for the first `early_engagement_window_hours = 2`, is what populates it — `app/jobs/early_engagement_job.py`).

> **Implementer note — do NOT call `compute_velocity` from this module.** `compute_velocity` (`derived.py:39-51`) requires *two* snapshots; it is only ever invoked by the `early_engagement_job`, never on a single TrackedPost row. The reward function reads the **already-persisted** `row["engagement_velocity"]` value (the stored output of that job). On the common single-snapshot case the field is simply absent (`None`) and the renormalized-0.75 path fires (§3) — this is correct, expected behavior, not an error.

`engagement_velocity` is a rate in roughly the same units as `engagement_rate` (engagement per impression), so reuse the same saturating curve with the same reference:

```
R_velocity = saturate(engagement_velocity, ref = ENG_RATE_REFERENCE)   # same 0.05 anchor
```

If `engagement_velocity` is `None` (only one snapshot exists, or impressions did not grow between snapshots — see `compute_velocity` returning `None` when `Δimpressions ≤ 0`), `R_velocity` is treated as **absent** and the velocity term is dropped with weight redistribution (§3).

### 2.3 `R_reply` — reply quality (weight 0.15)

Replies are the highest-signal engagement (a reply costs more effort than a like and indicates the post provoked thought/conversation — the stated goal of these accounts). Reward the **share** of engagement that is replies, not the raw count (raw count is just reach again):

```
reply_share = reply_count / (like_count + reply_count + retweet_count + quote_count)
R_reply     = reply_share                              # already in [0, 1]
```

`reply_share` is naturally in `[0, 1]` and needs no squashing. If total engagement is `0`, `reply_share` is `0` (no signal, not a division error — guarded). Note we use the **share of engagement actions**, not `reply_rate` (which is `replies/impressions` and already folded into `R_engagement` via the numerator); reply *share* is an orthogonal "what kind of engagement" signal, deliberately distinct from "how much engagement."

### 2.4 The exact formula (reference implementation shape)

```python
ENG_RATE_REFERENCE = 0.05
W_ENGAGEMENT = 0.60
W_VELOCITY   = 0.25
W_REPLY      = 0.15

def _saturate(x: float, ref: float) -> float:
    if x <= 0:
        return 0.0
    return x / (x + ref)
```

(Full module in §4.)

---

## 3. Edge cases — resolved, every one

These are the failure modes LEARN must never see as a `0.0` masquerading as "this post was bad." The rule throughout: **distinguish "measured and bad" (reward 0.0) from "not enough data" (reward None).** A `None` post is *excluded* from the account average; a `0.0` post drags it down.

| Case | Detection | Reward result | Rationale |
|---|---|---|---|
| **Brand-new post, never polled** | `impression_count is None` | `None` (insufficient data) | No reach measured yet; not a verdict. The engagement job hasn't run for it. |
| **Zero reach** (`impression_count == 0`) | `impression_count == 0` | `None` (insufficient data) | Division undefined. Mirrors `compute_rates`, which already returns `None` rates when `impressions <= 0` (`derived.py:20-25`). A genuinely-zero-reach post is a delivery anomaly, not a quality signal. |
| **`engagement_rate` missing** but impressions > 0 | `engagement_rate is None` | recompute via `compute_rates(row)` on the fly | The stored rate may be stale/absent on older rows; recompute deterministically from the same counts rather than guess. |
| **Velocity absent** (1 snapshot, or flat impressions) | `engagement_velocity is None` | drop velocity term, **renormalize remaining weights** | Most posts in their first hour have no velocity yet. Penalizing them as `R_velocity = 0` would systematically punish recent posts. Renormalize: see below. |
| **Zero total engagement** (likes=replies=…=0) but impressions > 0 | engagement sum == 0 | `R_engagement = 0`, `R_reply = 0`, reward computed (likely ~0) | This *is* a measured outcome: shown to people, nobody engaged. Legitimately low reward, not `None`. |
| **Deleted post** (`is_deleted == True`) | row flag | use last-known metrics; reward as normal | `engagement_job`/`early_engagement_job` already stop polling deleted posts but keep last metrics (`post_registry.mark_deleted`). Final metrics are valid for reward. |
| **Account with no qualifying posts** | all posts `None` | `avg_post_reward = None` on `AccountMetricsDocument` | No signal yet; LEARN must treat `None` as "do not promote/demote." |

**Weight renormalization when velocity is absent** (the only term that legitimately drops out for healthy recent posts):

```
If engagement_velocity is None:
    denom = W_ENGAGEMENT + W_REPLY            # = 0.75
    post_reward = (W_ENGAGEMENT/denom)·R_engagement + (W_REPLY/denom)·R_reply
```

`R_engagement` and `R_reply` are *always* available once `impression_count > 0` (we recompute the rate if needed and reply_share is guarded), so no further renormalization branches are needed. Engagement is never dropped; if engagement can't be computed, the whole post reward is `None` (the impressions guard already caught it).

---

## 4. File-by-file plan

### 4.1 Files at a glance

| File | Change | One-line role |
|---|---|---|
| `app/reward/__init__.py` | **NEW** | Package marker for the reward module (greenfield). |
| `app/reward/reward_function.py` | **NEW** | Pure functions: `post_reward(row) -> float | None` + `account_avg_reward(rows) -> float | None`. No I/O, no X calls. |
| `app/jobs/metrics_job.py` | **CHANGED** | Compute per-post reward over the rows it *already* loads; fold the average into `AccountMetricsDocument`. |
| `app/models/metrics.py` | **CHANGED** | Add one field: `avg_post_reward: float | None = None`. |
| `app/metrics/derived.py` | **REUSED** | `compute_rates` (reach-normalized rate) + `compute_velocity` (early velocity) consumed verbatim; **not modified**. |
| `app/models/post_metric_snapshot.py` | **REUSED** | Source of the per-snapshot counts/rates; **not modified** — reward reads, never writes here. |
| `app/services/post_registry.py` | **REUSED** | `TrackedPostRepository.list_for_account` provides the rows; **not modified**. |
| `tests/unit/test_reward_function.py` | **NEW** | Unit tests for the pure reward math + every edge case in §3. |

> **Module location note (Decision Defense §6).** The task brief names `reward/reward_function.py`. We honor it as `app/reward/reward_function.py` — a sibling of `app/metrics/`. The reward functions could arguably live in `app/metrics/derived.py` (where `compute_rates`/`compute_velocity` already are), but a dedicated `app/reward/` package keeps the Interpreter's MEASURE→LEARN→BUILD layers discoverable as their own namespace and signals "this is the contract LEARN consumes." `derived.py` stays the low-level primitive library; `reward/` composes it.

### 4.2 NEW — `app/reward/reward_function.py`

Pure, dependency-light, unit-testable. Takes a **TrackedPost row dict** (the exact shape `TrackedPostRepository.list_for_account` returns) and returns a reward or `None`. Reuses `compute_rates` for the on-the-fly recompute fallback.

```python
"""Normalized per-post reward for the Interpreter MEASURE phase.

Pure functions over already-polled metric rows. NO X-API calls, NO I/O.
Consumes the reach-normalized engagement_rate and engagement_velocity that the
engagement jobs already compute and store (see app/metrics/derived.py).

reward in [0, 1]; None means "insufficient data" (exclude from averages),
NOT "bad post" (which is a real, low, non-None reward).
"""

from __future__ import annotations

from typing import Any

from app.metrics.derived import compute_rates

# --- Tunable defaults (chosen, not fit; one account, few posts) ---
ENG_RATE_REFERENCE = 0.05   # engagement rate that maps to R=0.5 ("good" X post)
W_ENGAGEMENT = 0.60
W_VELOCITY = 0.25
W_REPLY = 0.15


def _num(value: Any) -> float:
    if isinstance(value, bool):           # bool is an int subclass; exclude
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _saturate(x: float, ref: float) -> float:
    """Monotonic, bounded squash: 0->0, ref->0.5, inf->1. ref must be > 0."""
    if x <= 0:
        return 0.0
    return x / (x + ref)


def _engagement_rate(row: dict[str, Any]) -> float | None:
    """Stored rate if present, else recompute deterministically from counts."""
    rate = row.get("engagement_rate")
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        return float(rate)
    return compute_rates(row).get("engagement_rate")  # None if impressions <= 0


def post_reward(row: dict[str, Any]) -> float | None:
    """Normalized reward in [0, 1], or None if there is not enough data.

    Insufficient data == no measured reach (impression_count missing or 0).
    Everything else yields a real number, including a legitimate ~0 for a
    post that reached people but earned no engagement.
    """
    impressions = row.get("impression_count")
    if not isinstance(impressions, (int, float)) or isinstance(impressions, bool):
        return None
    if impressions <= 0:
        return None

    e = _engagement_rate(row)
    if e is None:                          # impressions guard already passed, but be safe
        return None
    r_eng = _saturate(e, ENG_RATE_REFERENCE)

    likes = _num(row.get("like_count"))
    replies = _num(row.get("reply_count"))
    retweets = _num(row.get("retweet_count"))
    quotes = _num(row.get("quote_count"))
    total_eng = likes + replies + retweets + quotes
    r_reply = (replies / total_eng) if total_eng > 0 else 0.0

    vel = row.get("engagement_velocity")
    if isinstance(vel, (int, float)) and not isinstance(vel, bool):
        r_vel = _saturate(float(vel), ENG_RATE_REFERENCE)
        return W_ENGAGEMENT * r_eng + W_VELOCITY * r_vel + W_REPLY * r_reply

    # Velocity absent (common for fresh posts): drop its term, renormalize.
    denom = W_ENGAGEMENT + W_REPLY
    return (W_ENGAGEMENT / denom) * r_eng + (W_REPLY / denom) * r_reply


def account_avg_reward(rows: list[dict[str, Any]]) -> float | None:
    """Mean of per-post rewards, excluding posts with insufficient data (None).

    Returns None if no post qualifies — LEARN must read None as
    'no signal; do not promote or demote', never as 0.
    """
    scored = [r for r in (post_reward(row) for row in rows) if r is not None]
    if not scored:
        return None
    return sum(scored) / len(scored)
```

### 4.3 CHANGED — `app/models/metrics.py`

Add exactly one field to `AccountMetricsDocument` (currently `metrics.py:8-21`). It rides the same document the metrics job already writes — **no new collection, no new repository.**

```python
class AccountMetricsDocument(BaseModel):
    account_id: str
    computed_at: str
    avg_engagement_rate: float | None = None
    avg_reply_rate: float | None = None
    avg_like_rate: float | None = None
    avg_follower_delta: float | None = None
    positive_delta_avg_engagement: float | None = None
    non_positive_delta_avg_engagement: float | None = None
    follower_delta_engagement_gap: float | None = None
    avg_post_reward: float | None = None        # NEW: MEASURE-phase composite reward, [0,1] or None
    ...
```

`exclude_none=True` is already used when persisting (`metrics_job.py:53`), so the field is simply absent on documents where reward is `None` — no migration needed.

### 4.4 CHANGED — `app/jobs/metrics_job.py`

The metrics job already loads `rows = trepo.list_for_account(acc.account_id)` (`metrics_job.py:23`) and aggregates them — **the exact rows reward needs are already in memory.** Add one call and one field. No new query, no new X call.

```python
# at top of file
from app.reward.reward_function import account_avg_reward
```

```python
# inside the per-account loop, after `rows = trepo.list_for_account(acc.account_id)`:
        avg_reward = account_avg_reward(rows)

        doc = AccountMetricsDocument(
            account_id=acc.account_id,
            computed_at=datetime.now(timezone.utc).isoformat(),
            avg_engagement_rate=_avg(engagement_rates),
            avg_reply_rate=_avg(reply_rates),
            avg_like_rate=_avg(like_rates),
            avg_follower_delta=_avg(deltas),
            positive_delta_avg_engagement=_avg(pos_eng),
            non_positive_delta_avg_engagement=_avg(non_pos_eng),
            follower_delta_engagement_gap=_gap(_avg(pos_eng), _avg(non_pos_eng)),
            avg_post_reward=avg_reward,        # NEW
        )
```

That is the entire integration. The job's cadence (`CronTrigger(minute="10")`, hourly — `main.py:80`) is unchanged; reward recomputes hourly from whatever the engagement jobs have polled by then.

> **Per-post reward storage decision (Decision Defense §6):** we do **not** persist `post_reward` onto each `TrackedPostDocument` in this doc. The per-post reward is a pure deterministic function of fields already on the row (`impression_count`, counts, `engagement_velocity`), so it is recomputed on demand in O(1) and never goes stale. Storing it would create a second source of truth that the engagement jobs would have to keep updated on every metric refresh — exactly the kind of write-amplification we are avoiding. LEARN (doc `09`) calls `post_reward(row)` directly when it needs per-post granularity (e.g. grouping by `voice_version_hash`); the account average is the only value persisted, because that is what the aggregation job naturally produces.

---

## 5. How LEARN (doc `09`) consumes this — the contract

This is the seam. Doc `09` may rely on exactly these guarantees:

1. **`AccountMetricsDocument.avg_post_reward: float | None`** — refreshed hourly by `run_metrics_job`. `None` ⇒ no signal; never demote/promote on `None`.
2. **`reward.reward_function.post_reward(row) -> float | None`** — call directly for per-post granularity (e.g. average reward grouped by `creation_metrics.voice_version_hash`, or by `run_id`/`pipeline_hash` once doc `02` adds them). Same `[0,1]`/`None` contract.
3. **`reward.reward_function.account_avg_reward(rows) -> float | None`** — for ad-hoc averages over an arbitrary row subset (e.g. only posts from a challenger spec window).

Shared constants (`ENG_RATE_REFERENCE`, weights) are importable from `reward.reward_function` so LEARN's A/B comparison uses the identical scale. **LEARN owns the join** of reward → spec version; this doc owns only reward → tweet.

---

## 6. Decision Defense (non-obvious choices)

**Why ride `run_metrics_job` instead of a new reward job or per-tick computation?**
The single hardest constraint on this subsystem is the prior X-API cost blowup from over-frequent polling (`MEMORY.md`). Reward needs **no** new data — only arithmetic over rows the engagement jobs already wrote. `run_metrics_job` is *already* a pure-RavenDB aggregator that makes zero X calls (`metrics_job.py` calls only `trepo.list_for_account` + `client.put_document`), runs hourly, and *already loads the exact rows*. Adding reward there is a two-line change with zero marginal X cost and zero new scheduling. A dedicated reward job would duplicate the load; per-tick computation would recompute on every posting tick for no benefit (reward only changes when *metrics* refresh, which the engagement jobs drive, not the posting tick).

**Why `x / (x + ref)` and not min-max, percentile, or z-score normalization?**
Min-max needs a known max (we don't have one; a single viral post would rescale everything). Percentile/z-score need a population and re-rank every post when a new one lands (non-deterministic, order-dependent, overfits at N≈tens). `x/(x+ref)` is per-post, stateless, monotonic, bounded, and has **one** interpretable parameter (the rate that maps to 0.5). It is the elegant minimum that satisfies "normalized, comparable, in [0,1]" without a fitted model we can't yet justify.

**Why weight engagement 0.60 / velocity 0.25 / reply 0.15?**
Engagement rate is the most robust signal (largest sample, reach-normalized, always available) → dominant weight. Velocity is informative but noisy and frequently absent early → meaningful but secondary. Reply *share* is the highest-intent signal but lowest-volume and easily zero on small posts → smallest weight so a single reply doesn't dominate. These are deliberate priors, documented as tunable constants, to be revisited with data — not silent magic numbers.

**Why `None` (exclude) rather than `0.0` for insufficient data?**
A `0.0` for an unpolled or zero-reach post would *lie* to LEARN: it would look like a measured failure and drag down a spec's average, biasing the Interpreter against recently-deployed specs (whose posts are newest and least-polled). `None` + exclude-from-average keeps the average honest: it reflects only posts we actually measured. This mirrors `compute_rates` already returning `None` rather than `0` when impressions are missing.

**Why recompute `engagement_rate` on the fly instead of trusting the stored value?**
The stored rate can be `None`/stale on older rows or rows written before a counts refresh. Recomputing via the *same* `compute_rates` used everywhere else guarantees the reward uses a rate consistent with the live counts on the row, with no extra I/O. If impressions are missing/zero, `compute_rates` returns `None` and the impressions guard has already returned `None` anyway.

---

## 7. Definition of Done (this slice)

- [ ] `app/reward/__init__.py` and `app/reward/reward_function.py` exist; `python -m py_compile` clean.
- [ ] `app/models/metrics.py` `AccountMetricsDocument` has `avg_post_reward: float | None = None`.
- [ ] `app/jobs/metrics_job.py` imports `account_avg_reward`, calls it on the already-loaded `rows`, and sets `avg_post_reward` on the document. **No new query, no `TwitterService`/X call added** (grep the diff: zero new `tw.`/`get_posts_metrics`/`requests` references).
- [ ] `tests/unit/test_reward_function.py` green, covering:
  - reach-normalized engagement: `engagement_rate = ref (0.05)` ⇒ `R_engagement = 0.5`; monotonic increase.
  - reply share: `{like:10, reply:0,...}` ⇒ `R_reply = 0`; `{reply:5, like:5,...}` ⇒ `reply_share = 0.5`.
  - velocity present vs absent: identical counts with/without `engagement_velocity` produce a reward in `[0,1]` both ways; absent path uses the renormalized 0.75 denominator (assert the two differ as expected, not that absent ⇒ 0).
  - `impression_count` missing ⇒ `None`; `impression_count == 0` ⇒ `None` (insufficient data, NOT 0.0).
  - zero engagement but `impression_count > 0` ⇒ a real number near `0`, **not** `None`.
  - `account_avg_reward`: a mix of scored + `None` posts averages only the scored; all-`None` ⇒ `None`.
  - every returned reward (non-None) is within `[0.0, 1.0]`.
- [ ] Full `pytest` green (the existing `tests/unit/test_derived_metrics.py` is untouched and still passes — `derived.py` is read-only here).
- [ ] Manual sanity: `run_metrics_job()` against the `JohnJames_News` data writes `accountmetrics/JohnJames_News` with an `avg_post_reward` that is either a float in `[0,1]` or absent (when all posts are unpolled). Confirm no new X requests fire (the job makes none).

---

## 8. Sibling-doc references

- **doc `09` (LEARN — Champion/Challenger Evaluation + Self-Rewrite):** consumes `avg_post_reward` + `post_reward(row)`; owns the reward→spec-version join (groups by `voice_version_hash` now, by `run_id`/`pipeline_hash` after doc `02`). Shared scale via the constants exported here. (Doc `09` reads the per-`pipeline_hash` reward off the `OutcomeLedgerDocument` that doc `02` builds; this doc only supplies the reward *scalar*, never the join.)
- **doc `02` (attribution — Outcome Ledger + Attribution Join):** adds the optional `run_id` + `pipeline_hash` fields to `PostCreationMetrics` (`models/tracked_post.py:10-25`) and threads them through `finalize_post`. Not required for *this* doc — reward keys by `tweet_id` — but is the field LEARN joins on. We deliberately do not block on it.

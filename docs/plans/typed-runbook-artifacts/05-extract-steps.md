# Task 5: extract-steps

## Section 1 – Task Overview

### Goal

Refactor `app/pipeline/services/steps.py` with **renamed ingest steps** and **four new analysis steps** extracted from subagents; move shared logic to **new** `app/pipeline/services/reference_analysis.py`.

### Gathered context

**Current `steps.py`** — five thin wrappers, no rank/brief:

```13:88:SocialMediaAutonomousAgents/backend/app/pipeline/services/steps.py
def profile(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    return tool_catalog().data.account_profile.run(ctx, tick_data=deps.tick_data)
# ... timeline_pool, search_pool, merge_reference_pools, own_posts_pool
```

**Timeline subagent** bundles rank + LLM brief (~50 lines):

```21:70:SocialMediaAutonomousAgents/backend/app/pipeline/subagents/timeline.py
def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    """Rank top timeline references and produce a pattern brief."""
    refs_payload = ctx.get("timeline_references")
    # ... optional refetch, URL filter, reference_rank, reference_pattern_summary ...
    ctx.set("timeline_analysis", brief)
    return StepResult(ok=True, payload={"timeline_analysis": brief, "winner": winner})
```

**Own-posts subagent** — parallel structure with `MIN_POSTS = 3` guard:

```20:69:SocialMediaAutonomousAgents/backend/app/pipeline/subagents/own_posts.py
def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    # ... own_posts_fetch fallback, rank, pattern summary ...
    ctx.set("own_posts_analysis", brief)
    return StepResult(ok=True, payload={"own_posts_analysis": brief})
```

Duplicated helpers: `_enrich_row_features`, `_top_entities`, `_avg_char_count` in both subagents.

### Step id mapping (locked: expanded rank+brief)

| Old | New step id |
|-----|-------------|
| `profile` | `load_account_bundle` |
| `timeline_pool` | `fetch_timeline_references` |
| `search_pool` | `fetch_search_references` |
| `merge_reference_pools` | `merge_external_references` |
| `own_posts_pool` | `fetch_own_post_history` |
| *(inside timeline.run)* | `rank_external_references`, `brief_external_references` |
| *(inside own_posts.run)* | `rank_own_posts`, `brief_own_posts` |

### Location / dependencies

| Path | Role |
|------|------|
| `services/steps.py` | Renamed + new step functions |
| `services/reference_analysis.py` | **New** — shared helpers |
| `subagents/timeline.py`, `subagents/own_posts.py` | Slim to delegate to new steps (task 5 tail) |
| Tasks 4, 6, 7 | Tools migrated; engine + runbook consume new step ids |

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

1. Create `reference_analysis.py` with pool extraction, URL filter, row enrichment, entity/char helpers, auth user id, tracked-row normalization.
2. Rename existing step functions (keep thin wrapper pattern).
3. Add `rank_external_references`, `brief_external_references`, `rank_own_posts`, `brief_own_posts` using `require_artifact` / migrated tools.
4. Preserve skip semantics: no URLs → skip rank path with `timeline_analysis` skip brief; `<3 own posts` → skip with `own_posts_analysis`.

### b. Before Panel

**steps.py** (full current file):

```1:88:SocialMediaAutonomousAgents/backend/app/pipeline/services/steps.py
"""Thin step wrappers — hide tool argument wiring from the runbook."""

from __future__ import annotations

from app.core.config import settings
from app.pipeline.accessors import tool_catalog
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService


def profile(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    return tool_catalog().data.account_profile.run(ctx, tick_data=deps.tick_data)


def timeline_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    bundle = ctx.get("account_bundle") or {}
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    auth_id = str(prof.get("id")) if isinstance(prof, dict) and prof.get("id") is not None else None
    return tool_catalog().data.timeline_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        authenticated_user_id=auth_id,
    )


def _authenticated_user_id(ctx: TickRunContext) -> str | None:
    bundle = ctx.get("account_bundle") or {}
    prof = bundle.get("profile") if isinstance(bundle, dict) else {}
    if isinstance(prof, dict) and prof.get("id") is not None:
        return str(prof["id"])
    return None


def search_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if not settings.trend_tweet_search_enabled:
        return StepResult(ok=True, skipped=True, skip_reason="search_disabled")
    acc = deps.repo.load(ctx.account_id)
    if acc is None:
        return StepResult(ok=False, skip_reason="account_not_found")
    queries = list(acc.search_queries or [])
    if not queries:
        return StepResult(ok=True, skipped=True, skip_reason="no_search_queries")
    return tool_catalog().data.search_fetch.run(
        ctx,
        tick_data=deps.tick_data,
        queries=queries,
        authenticated_user_id=_authenticated_user_id(ctx),
    )


def merge_reference_pools(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    _ = deps
    timeline_payload = dict(ctx.get("timeline_references") or {})
    search_payload = ctx.get("search_references") or {}
    # ... merge logic ...
    ctx.set("timeline_references", timeline_payload)
    return StepResult(ok=True, payload={...})


def own_posts_pool(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    if deps.post_registry is None:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry")
    return tool_catalog().data.own_posts_fetch.run(ctx, post_registry=deps.post_registry)
```

**reference_analysis.py:** **(new file)**

### c. After Panel

**reference_analysis.py** (new file — full):

```python
"""Shared helpers for rank/brief reference analysis steps."""

from __future__ import annotations

from typing import Any

from app.metrics.derived import extract_entities, extract_text_features
from app.pipeline.types.artifacts import AccountBundle, ArtifactKey, OwnPostsPayload, TimelineReferencesPayload
from app.pipeline.types.context import TickRunContext
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls

MIN_OWN_POSTS = 3
MIN_TOP_N = 10


def authenticated_user_id(ctx: TickRunContext) -> str | None:
    """Read profile id from typed account_bundle artifact."""
    bundle = ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE)
    if bundle is None:
        return None
    prof = bundle.profile if isinstance(bundle, AccountBundle) else None
    if isinstance(prof, dict) and prof.get("id") is not None:
        return str(prof["id"])
    return None


def external_pool_rows(ctx: TickRunContext) -> list[dict[str, Any]]:
    """Merge timeline_references payload and keep only URL-bearing rows."""
    refs = ctx.require_artifact(ArtifactKey.TIMELINE_REFERENCES)
    payload = refs.model_dump() if hasattr(refs, "model_dump") else refs
    pool = TickDataService.merge_reference_pool(payload)
    return filter_rows_with_urls(pool)


def own_post_rows(ctx: TickRunContext) -> list[dict[str, Any]]:
    """Normalize TrackedPost documents into reference-rank rows."""
    own = ctx.require_artifact(ArtifactKey.OWN_POSTS)
    posts = own.posts if isinstance(own, OwnPostsPayload) else (own.get("posts") or [])
    rows: list[dict[str, Any]] = []
    for doc in posts:
        if not isinstance(doc, dict):
            continue
        text = str(doc.get("post_text") or doc.get("text") or "").strip()
        raw = doc.get("raw_metrics") if isinstance(doc.get("raw_metrics"), dict) else {}
        row = {
            "tweet_id": doc.get("tweet_id"),
            "id": doc.get("tweet_id"),
            "text": text or str(raw.get("text") or ""),
            "like_count": doc.get("like_count") if doc.get("like_count") is not None else raw.get("like_count"),
            "reply_count": doc.get("reply_count") if doc.get("reply_count") is not None else raw.get("reply_count"),
            "retweet_count": doc.get("retweet_count") if doc.get("retweet_count") is not None else raw.get("retweet_count"),
            "quote_count": doc.get("quote_count") if doc.get("quote_count") is not None else raw.get("quote_count"),
            "impression_count": doc.get("impression_count")
            if doc.get("impression_count") is not None
            else raw.get("impression_count"),
            "posted_at": doc.get("posted_at"),
            "source": "own_posts",
        }
        if row.get("tweet_id"):
            rows.append(row)
    return rows


def enrich_row_features(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["text_features"] = extract_text_features(str(out.get("text") or ""))
    out["entity_tags"] = extract_entities(out)
    return out


def top_entities(rows: list[dict[str, Any]], limit: int = 12) -> list[str]:
    tags: list[str] = []
    for r in rows:
        for t in r.get("entity_tags") or []:
            if isinstance(t, str) and t.strip():
                tags.append(t.strip())
    seen: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen[:limit]


def avg_char_count(rows: list[dict[str, Any]]) -> float | None:
    counts = []
    for r in rows:
        tf = r.get("text_features")
        if isinstance(tf, dict):
            cc = tf.get("char_count")
            if isinstance(cc, int):
                counts.append(cc)
    if not counts:
        return None
    return float(sum(counts)) / float(len(counts))


def skip_brief(source: str, skip_reason: str, **extra: Any) -> dict[str, Any]:
    """Standard skipped ReferencePatternBrief-shaped dict."""
    return {"skipped": True, "skip_reason": skip_reason, "source": source, **extra}
```

**steps.py** (key excerpts — full file replaces old names and adds four steps):

```python
from app.pipeline.services import reference_analysis as ref
from app.pipeline.types.artifacts import ArtifactKey, ReferencePatternBrief

# Renamed ingest steps
def load_account_bundle(ctx, deps):
    return tool_catalog().data.account_profile.run(ctx, tick_data=deps.tick_data)

def fetch_timeline_references(ctx, deps):
    return tool_catalog().data.timeline_fetch.run(
        ctx, tick_data=deps.tick_data, authenticated_user_id=ref.authenticated_user_id(ctx),
    )

def fetch_search_references(ctx, deps):
    # same guards as search_pool ...
    return tool_catalog().data.search_fetch.run(...)

def merge_external_references(ctx, deps):
    # require_artifact TIMELINE_REFERENCES + SEARCH_REFERENCES (search optional empty)
    timeline_payload = ctx.require_artifact(ArtifactKey.TIMELINE_REFERENCES).model_dump()
    search_raw = ctx.get_artifact(ArtifactKey.SEARCH_REFERENCES)
    search_payload = search_raw.model_dump() if search_raw else {}
    merged = TickDataService.merge_reference_pool_rows(...)
    timeline_payload["timeline_reference_tweets"] = merged
    # ... metadata fields unchanged ...
    ctx.set_artifact(ArtifactKey.TIMELINE_REFERENCES, timeline_payload)
    return StepResult(ok=True, payload={...})

def fetch_own_post_history(ctx, deps):
    # same as own_posts_pool ...

def rank_external_references(ctx, deps) -> StepResult:
    pool = ref.external_pool_rows(ctx)
    if not pool:
        brief = ref.skip_brief("timeline", "no_reference_with_urls")
        ctx.set_artifact(ArtifactKey.TIMELINE_ANALYSIS, brief)
        return StepResult(ok=True, skipped=True, skip_reason="no_reference_with_urls", payload=brief)
    return tool_catalog().deterministic.reference_rank.run(
        ctx, rows=pool, top_n=ref.MIN_TOP_N, artifact_key=ArtifactKey.TIMELINE_RANKED,
    )

def brief_external_references(ctx, deps) -> StepResult:
    ranked_art = ctx.get_artifact(ArtifactKey.TIMELINE_RANKED)
    if ranked_art is None:
        return StepResult(ok=True, skipped=True, skip_reason="rank_skipped")
    ranked = [ref.enrich_row_features(r) for r in (ranked_art.model_dump().get("ranked") or []) if isinstance(r, dict)]
    tool_catalog().llm.reference_pattern_summary.run(
        ctx, source="timeline", niche=ctx.niche, top_posts=ranked,
        features={"pool_size": len(ref.external_pool_rows(ctx)), "top_n": len(ranked), ...},
        artifact_key=ArtifactKey.TIMELINE_ANALYSIS,
    )
    brief = ctx.get_artifact(ArtifactKey.TIMELINE_ANALYSIS)
    winner = ranked_art.model_dump().get("winner") if ranked_art else None
    if brief and winner and isinstance(winner := winner, dict):
        dumped = brief.model_dump() if hasattr(brief, "model_dump") else dict(brief)
        dumped["selected_winner_id"] = winner.get("tweet_id")
        ctx.set_artifact(ArtifactKey.TIMELINE_ANALYSIS, dumped)
    return StepResult(ok=True, payload={"timeline_analysis": ctx.get("timeline_analysis")})

def rank_own_posts(ctx, deps) -> StepResult:
    if deps.post_registry is None:
        brief = ref.skip_brief("own_posts", "no_post_registry")
        ctx.set_artifact(ArtifactKey.OWN_POSTS_ANALYSIS, brief)
        return StepResult(ok=True, skipped=True, skip_reason="no_post_registry", payload=brief)
    rows = ref.own_post_rows(ctx)
    if len(rows) < ref.MIN_OWN_POSTS:
        brief = ref.skip_brief("own_posts", "insufficient_own_posts", post_count=len(rows))
        ctx.set_artifact(ArtifactKey.OWN_POSTS_ANALYSIS, brief)
        return StepResult(ok=True, skipped=True, skip_reason="insufficient_own_posts", payload=brief)
    return tool_catalog().deterministic.reference_rank.run(
        ctx, rows=rows, top_n=ref.MIN_TOP_N, artifact_key=ArtifactKey.OWN_POSTS_RANKED,
    )

def brief_own_posts(ctx, deps) -> StepResult:
    # mirror brief_external_references for own_posts source / OWN_POSTS_ANALYSIS
    ...

# Backward-compat aliases until callers updated (optional, remove in task 8):
profile = load_account_bundle
timeline_pool = fetch_timeline_references
search_pool = fetch_search_references
merge_reference_pools = merge_external_references
own_posts_pool = fetch_own_post_history
```

**Slim subagents** (after):

```python
# subagents/timeline.py
from app.pipeline.services import steps

def run(ctx, deps):
    rank = steps.rank_external_references(ctx, deps)
    if rank.skipped or not rank.ok:
        return rank
    return steps.brief_external_references(ctx, deps)
```

### d. Written explanation connecting changes to broader picture

Extracting rank/brief makes the runbook **honest about work units**: deterministic scoring vs LLM summarization become separate logged steps with distinct artifact writes. Shared helpers eliminate subagent duplication and give one place for URL-filter and TrackedPost normalization rules. Renamed ingest steps align human-readable runbook text with data products (`fetch_timeline_references` produces `timeline_references`). Subagents remain as compatibility shims for `from app.pipeline import subagents`.

---

## Section 3 – Decision Defense

### Chosen path: four explicit steps + shared module

| Alternative | Why not chosen |
|-------------|----------------|
| **Keep subagents as runbook entries** | Violates locked expanded-step decision; hides I/O. |
| **One `analyze_*` step each** | Still collapses rank vs LLM; harder to test/skip independently. |
| **Inline helpers in steps.py** | Duplication across external/own branches; reference_analysis.py is clearer. |

### Rank step sets analysis artifact on skip

When no URL pool, `rank_external_references` writes skipped `timeline_analysis` so downstream compose/`reference_phase` behavior matches today's subagent (which set analysis before returning skipped `StepResult`).

### Backward-compat aliases in steps.py

Optional short-term aliases prevent breaking tests before task 8 updates; grep should target new names only.

### Frontend

**N/A** — backend step layer only.

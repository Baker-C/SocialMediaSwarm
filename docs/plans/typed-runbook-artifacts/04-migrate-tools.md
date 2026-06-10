# Task 4: migrate-tools

## Section 1 – Task Overview

### Goal

Update six pipeline tools that write run context to use **`ctx.set_artifact(ArtifactKey.*, ...)`** instead of raw `ctx.set`, and add **`TOOL_WRITES`** / **`OUTPUT_MODEL`** metadata for catalog discoverability.

### Tools in scope

| Module | Current write key | Target `ArtifactKey` |
|--------|-----------------|---------------------|
| `tools/data/account_profile.py` | `account_bundle` | `ACCOUNT_BUNDLE` |
| `tools/data/timeline_fetch.py` | `timeline_references` | `TIMELINE_REFERENCES` |
| `tools/data/search_fetch.py` | `search_references` | `SEARCH_REFERENCES` |
| `tools/data/own_posts_fetch.py` | `own_posts` | `OWN_POSTS` |
| `tools/deterministic/reference_rank.py` | dynamic `store_key` | `TIMELINE_RANKED` / `OWN_POSTS_RANKED` |
| `tools/llm/reference_pattern_summary.py` | dynamic `store_key` | `TIMELINE_ANALYSIS` / `OWN_POSTS_ANALYSIS` |

### Gathered context

All data tools follow the same pattern—fetch/build dict, `ctx.set`, return `StepResult`:

```17:26:SocialMediaAutonomousAgents/backend/app/pipeline/tools/data/account_profile.py
def run(
    ctx: TickRunContext,
    *,
    tick_data: TickDataService,
    account_id: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    bundle = tick_data.compile_account_bundle(aid)
    ctx.set("account_bundle", bundle)
    return StepResult(ok=True, payload={"account_bundle": bundle})
```

`reference_rank` parameterizes storage:

```21:35:SocialMediaAutonomousAgents/backend/app/pipeline/tools/deterministic/reference_rank.py
def run(
    ctx: TickRunContext,
    *,
    rows: list[dict[str, Any]],
    top_n: int = 10,
    exclude_ids: frozenset[str] | None = None,
    store_key: str = "ranked_references",
) -> StepResult:
    ranked = rank_rows(rows, top_n=top_n, exclude_ids=exclude_ids)
    payload = {
        "ranked": [t.model_dump() for t in ranked],
        "winner": ranked[0].model_dump() if ranked else None,
    }
    ctx.set(store_key, payload)
    return StepResult(ok=True, payload=payload)
```

Subagents pass `store_key="timeline_ranked"` / `"own_posts_ranked"` and analysis keys similarly.

### Location / dependencies

- **Depends on tasks 1 + 3** (models + `set_artifact`).
- **Precedes task 5** — extracted rank/brief steps call these tools.
- **`fetch()` helpers** on data tools unchanged—they do not touch context.

### What it affects

- Invalid tick-data shapes fail at tool boundary with Pydantic errors.
- `reference_rank` / `reference_pattern_summary` should accept `ArtifactKey` (preferred) or map legacy `store_key` strings for backward compat inside subagent wrappers.

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

For each tool:

1. Import `ArtifactKey` and `OUTPUT_MODEL` type from `artifacts.py`.
2. Declare module-level `TOOL_WRITES: tuple[ArtifactKey, ...]`.
3. Replace `ctx.set(...)` with `ctx.set_artifact(ArtifactKey.X, payload)`.
4. For rank/summary tools: add `artifact_key: ArtifactKey | None = None` parameter; map `store_key` string → `ArtifactKey` when `artifact_key` omitted.

### b. Before Panel

**account_profile.py** (representative data tool):

```1:31:SocialMediaAutonomousAgents/backend/app/pipeline/tools/data/account_profile.py
"""Fetch account profile and tracked-post engagement metrics."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService

TOOL_ID = "data.account_profile"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Load X profile and tracked-post engagement metrics for an account"


def run(
    ctx: TickRunContext,
    *,
    tick_data: TickDataService,
    account_id: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    bundle = tick_data.compile_account_bundle(aid)
    ctx.set("account_bundle", bundle)
    return StepResult(ok=True, payload={"account_bundle": bundle})


def fetch(tick_data: TickDataService, account_id: str) -> dict[str, Any]:
    """Direct helper for callers that do not use TickRunContext yet."""
    return tick_data.compile_account_bundle(account_id)
```

**reference_rank.py** (dynamic key):

```21:35:SocialMediaAutonomousAgents/backend/app/pipeline/tools/deterministic/reference_rank.py
def run(
    ctx: TickRunContext,
    *,
    rows: list[dict[str, Any]],
    top_n: int = 10,
    exclude_ids: frozenset[str] | None = None,
    store_key: str = "ranked_references",
) -> StepResult:
    ranked = rank_rows(rows, top_n=top_n, exclude_ids=exclude_ids)
    payload = {
        "ranked": [t.model_dump() for t in ranked],
        "winner": ranked[0].model_dump() if ranked else None,
    }
    ctx.set(store_key, payload)
    return StepResult(ok=True, payload=payload)
```

**reference_pattern_summary.py** (dynamic key):

```21:33:SocialMediaAutonomousAgents/backend/app/pipeline/tools/llm/reference_pattern_summary.py
def run(
    ctx: TickRunContext,
    *,
    source: SourceLabel,
    niche: str,
    top_posts: list[dict[str, Any]],
    features: dict[str, Any] | None = None,
    store_key: str | None = None,
) -> StepResult:
    summary = summarize(source=source, niche=niche, top_posts=top_posts, features=features or {})
    key = store_key or f"{source}_pattern_summary"
    ctx.set(key, summary)
    return StepResult(ok=True, payload=summary)
```

*(timeline_fetch, search_fetch, own_posts_fetch follow the same `ctx.set` pattern as account_profile.)*

### c. After Panel

**account_profile.py** (pattern for all data tools):

```python
from app.pipeline.types.artifacts import AccountBundle, ArtifactKey
# ...

TOOL_WRITES = (ArtifactKey.ACCOUNT_BUNDLE,)
OUTPUT_MODEL = AccountBundle

def run(...) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    bundle = tick_data.compile_account_bundle(aid)
    ctx.set_artifact(ArtifactKey.ACCOUNT_BUNDLE, bundle)  # validates AccountBundle shape
    return StepResult(ok=True, payload={"account_bundle": bundle})
```

**timeline_fetch.py:**

```python
TOOL_WRITES = (ArtifactKey.TIMELINE_REFERENCES,)
OUTPUT_MODEL = TimelineReferencesPayload

def run(...) -> StepResult:
    # ...
    ctx.set_artifact(ArtifactKey.TIMELINE_REFERENCES, payload)
    return StepResult(ok=True, payload={"timeline_references": payload})
```

**search_fetch.py:**

```python
TOOL_WRITES = (ArtifactKey.SEARCH_REFERENCES,)
OUTPUT_MODEL = SearchReferencesPayload

def run(...) -> StepResult:
    ctx.set_artifact(ArtifactKey.SEARCH_REFERENCES, payload)
```

**own_posts_fetch.py:**

```python
TOOL_WRITES = (ArtifactKey.OWN_POSTS,)
OUTPUT_MODEL = OwnPostsPayload

def run(...) -> StepResult:
    ctx.set_artifact(ArtifactKey.OWN_POSTS, payload)
```

**reference_rank.py:**

```python
from app.pipeline.types.artifacts import ARTIFACT_KEY_BY_CTX_KEY, ArtifactKey, RankedReferencesPayload

TOOL_WRITES = (ArtifactKey.TIMELINE_RANKED, ArtifactKey.OWN_POSTS_RANKED)  # caller picks one
OUTPUT_MODEL = RankedReferencesPayload

_STORE_KEY_ALIASES: dict[str, ArtifactKey] = {
    "timeline_ranked": ArtifactKey.TIMELINE_RANKED,
    "own_posts_ranked": ArtifactKey.OWN_POSTS_RANKED,
    "ranked_references": ArtifactKey.TIMELINE_RANKED,  # legacy default
}

def _resolve_artifact_key(*, artifact_key: ArtifactKey | None, store_key: str) -> ArtifactKey:
    if artifact_key is not None:
        return artifact_key
    mapped = _STORE_KEY_ALIASES.get(store_key) or ARTIFACT_KEY_BY_CTX_KEY.get(store_key)
    if mapped is None:
        raise ValueError(f"Unknown reference rank store_key: {store_key!r}")
    return mapped

def run(
    ctx: TickRunContext,
    *,
    rows: list[dict[str, Any]],
    top_n: int = 10,
    exclude_ids: frozenset[str] | None = None,
    store_key: str = "ranked_references",
    artifact_key: ArtifactKey | None = None,
) -> StepResult:
    key = _resolve_artifact_key(artifact_key=artifact_key, store_key=store_key)
    ranked = rank_rows(rows, top_n=top_n, exclude_ids=exclude_ids)
    payload = {"ranked": [t.model_dump() for t in ranked], "winner": ranked[0].model_dump() if ranked else None}
    ctx.set_artifact(key, payload)  # RankedReferencesPayload validation
    return StepResult(ok=True, payload=payload)
```

**reference_pattern_summary.py:**

```python
from app.pipeline.types.artifacts import ArtifactKey, ReferencePatternBrief

TOOL_WRITES = (ArtifactKey.TIMELINE_ANALYSIS, ArtifactKey.OWN_POSTS_ANALYSIS)
OUTPUT_MODEL = ReferencePatternBrief

_ANALYSIS_KEYS: dict[SourceLabel, ArtifactKey] = {
    "timeline": ArtifactKey.TIMELINE_ANALYSIS,
    "own_posts": ArtifactKey.OWN_POSTS_ANALYSIS,
}

def run(
    ctx: TickRunContext,
    *,
    source: SourceLabel,
    niche: str,
    top_posts: list[dict[str, Any]],
    features: dict[str, Any] | None = None,
    store_key: str | None = None,
    artifact_key: ArtifactKey | None = None,
) -> StepResult:
    summary = summarize(source=source, niche=niche, top_posts=top_posts, features=features or {})
    key = artifact_key or _ANALYSIS_KEYS.get(source)
    if key is None and store_key:
        key = ARTIFACT_KEY_BY_CTX_KEY.get(store_key)
    if key is None:
        raise ValueError(f"Cannot resolve analysis artifact key for source={source!r}")
    ctx.set_artifact(key, summary)
    return StepResult(ok=True, payload=summary)
```

### d. Written explanation connecting changes to broader picture

Tools are the **lowest-level producers** of context artifacts. Migrating them first ensures every runbook step benefits from validation regardless of whether logic lives in `steps.py` or subagents. `TOOL_WRITES` enables future catalog lint (“tool declares writes matching step declarations”). Mapping legacy `store_key` strings preserves thin subagent wrappers until task 5 removes duplication.

---

## Section 3 – Decision Defense

### Chosen path: migrate tools before steps

| Alternative | Why not chosen |
|-------------|----------------|
| **Validate only in steps.py wrappers** | Tools callable directly from subagents/tests; bypass risk. |
| **Remove `store_key` immediately** | Breaks subagents before task 5 extraction; dual path is safer. |
| **Change tick_data to return models** | Larger blast radius; tools validate at context boundary. |

### Keep `fetch()` helpers untyped

External callers (`interval_crew`) use helpers without context; validation belongs at runbook boundary.

### Frontend

**N/A** — backend tool layer only.

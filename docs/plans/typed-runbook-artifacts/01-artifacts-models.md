# Task 1: artifacts-models

## Section 1 – Task Overview

### Goal

Introduce `app/pipeline/types/artifacts.py` as the **canonical typed contract** for every value stored in `TickRunContext.data` during the post-tick reference runbook. This file is the foundation for tasks 3–7: context accessors, tool migrations, step extraction, and runbook I/O declarations all depend on `ArtifactKey`, Pydantic models, and the `ARTIFACTS` registry.

### Gathered context

Today, runbook context is an untyped string-keyed bag:

```11:23:SocialMediaAutonomousAgents/backend/app/pipeline/types/context.py
@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
```

Developers infer artifact shapes by reading tool `ctx.set(...)` calls, subagent code, and `docs/subsystems/pipeline-runbook.md` context-key tables. There is no single source of truth and no validation at write time.

The reference runbook currently sets eight keys (documented in `docs/subsystems/pipeline-runbook.md` lines 173–184):

| Context key | Current producer |
|-------------|----------------|
| `account_bundle` | `steps.profile` → `data.account_profile` |
| `timeline_references` | `steps.timeline_pool`, `steps.merge_reference_pools` |
| `search_references` | `steps.search_pool` |
| `own_posts` | `steps.own_posts_pool` |
| `timeline_ranked` | `subagents/timeline.py` via `reference_rank` |
| `timeline_analysis` | `subagents/timeline.py` via `reference_pattern_summary` |
| `own_posts_ranked` | `subagents/own_posts.py` |
| `own_posts_analysis` | `subagents/own_posts.py` |

Payload shapes originate from `TickDataService.compile_*` return dicts, `GatheredTweet` (rank rows), and `reference_pattern_summary.summarize` output.

### Location in project

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/pipeline/types/artifacts.py` | **New** — models + registry |
| `SocialMediaAutonomousAgents/backend/app/pipeline/types/__init__.py` | Re-export `ArtifactKey`, models, `ARTIFACTS` |
| `SocialMediaAutonomousAgents/backend/tests/unit/test_artifacts.py` | **New** — contract fixture validation (task 8) |

### What it affects

- **Task 3** (`context.py`): `set_artifact` / `get_artifact` look up models via `ARTIFACTS`.
- **Task 4** (tool migration): tools declare `TOOL_WRITES` / `OUTPUT_MODEL` against these types.
- **Task 2** (`flow.py`): `Step.reads` / `Step.writes` use `ArtifactKey` enum members.
- **Downstream consumers unchanged at key level**: `reference_phase.py`, compose, and `RunbookResult.reference_context()` continue reading the same string keys in `ctx.data`.

### Related changes / dependencies

- **Locked decision**: context key strings stay unchanged (`account_bundle`, not `load_account_bundle_output`).
- Reuses `GatheredTweet` from `app/interval/tweet_topic_preanalysis.py` inside `RankedReferencesPayload`.
- All models use `ConfigDict(extra="allow")` so evolving X API / RavenDB fields do not break validation.
- Must land **before** strict `set_artifact` (task 3) and tool migration (task 4).

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

Create `artifacts.py` with:

1. **`ArtifactKey` (`StrEnum`)** — one member per context key; `.value` equals the existing string key.
2. **Pydantic row/payload models** — `ReferenceTweetRow`, `AccountBundle`, `TimelineReferencesPayload`, `SearchReferencesPayload`, `OwnPostsPayload`, `RankedReferencesPayload`, `ReferencePatternBrief`.
3. **`ArtifactDef` + `ARTIFACTS` registry** — maps each key to model, human purpose, and planned producer step id (for docs/tests).
4. **`ARTIFACT_KEY_BY_CTX_KEY` + `artifact_key_for_ctx_key()`** — bridge for legacy string lookups.
5. **`CONTRACT_FIXTURES`** — minimal valid dict per key for unit tests (task 8); invalid variants tested separately.

Export everything from `types/__init__.py`.

### b. Before Panel

**(new file)**

`app/pipeline/types/artifacts.py` does not exist in the pre-refactor baseline. Artifact shapes are implicit across tools, subagents, and subsystem docs.

Surrounding `types/` package today:

```1:5:SocialMediaAutonomousAgents/backend/app/pipeline/types/__init__.py
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult, ToolKind, ToolRun, ToolSpec

__all__ = ["StepResult", "TickRunContext", "ToolKind", "ToolRun", "ToolSpec"]
```

### c. After Panel

```python
"""Canonical Pydantic models for pipeline runbook context artifacts."""


from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.interval.tweet_topic_preanalysis import GatheredTweet

# Reused by ReferencePatternBrief.source — matches reference_pattern_summary.SourceLabel
SourceLabel = Literal["timeline", "own_posts"]


class ArtifactKey(StrEnum):
    """Enum members MUST match existing TickRunContext.data key strings (locked decision)."""

    ACCOUNT_BUNDLE = "account_bundle"
    TIMELINE_REFERENCES = "timeline_references"
    SEARCH_REFERENCES = "search_references"
    OWN_POSTS = "own_posts"
    TIMELINE_RANKED = "timeline_ranked"
    OWN_POSTS_RANKED = "own_posts_ranked"
    TIMELINE_ANALYSIS = "timeline_analysis"
    OWN_POSTS_ANALYSIS = "own_posts_analysis"


class ReferenceTweetRow(BaseModel):
    """One external reference tweet from X timeline or search."""

    model_config = ConfigDict(extra="allow")  # X/search rows carry evolving fields

    id: str | None = None
    tweet_id: str | None = None
    text: str = ""
    like_count: int | None = None
    reply_count: int | None = None
    retweet_count: int | None = None
    quote_count: int | None = None
    impression_count: int | None = None
    source: str | None = None
    search_query: str | None = None
    matched_queries: list[str] | None = None


class AccountBundle(BaseModel):
    """Shape of TickDataService.compile_account_bundle — profile + tracked metrics."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    profile: dict[str, Any] | None = None
    tracked_tweet_ids: list[str] = Field(default_factory=list)
    post_engagements: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TimelineReferencesPayload(BaseModel):
    """External reference pool; mutated by merge step (search metadata appended)."""

    model_config = ConfigDict(extra="allow")

    timeline_reference_tweets: list[ReferenceTweetRow | dict[str, Any]] = Field(default_factory=list)
    reference_errors: list[str] = Field(default_factory=list)
    search_merged_count: int | None = None
    timeline_only_count: int | None = None
    search_queries_run: list[str] | None = None
    pulled_tweet_stats: dict[str, Any] | None = None


class SearchReferencesPayload(BaseModel):
    """Output of compile_search_reference_tweets."""

    model_config = ConfigDict(extra="allow")

    search_reference_tweets: list[ReferenceTweetRow | dict[str, Any]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    per_query_counts: dict[str, int] = Field(default_factory=dict)
    reference_errors: list[str] = Field(default_factory=list)
    pulled_tweet_stats: dict[str, Any] | None = None


class OwnPostsPayload(BaseModel):
    """Own-post history from RavenDB via own_posts_fetch."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    tweet_ids: list[str] = Field(default_factory=list)
    posts: list[dict[str, Any]] = Field(default_factory=list)  # TrackedPost docs as dicts


class RankedReferencesPayload(BaseModel):
    """Top-N ranked rows + winner — shared by timeline and own-posts rank steps."""

    model_config = ConfigDict(extra="allow")

    ranked: list[GatheredTweet | dict[str, Any]] = Field(default_factory=list)
    winner: GatheredTweet | dict[str, Any] | None = None


class ReferencePatternBrief(BaseModel):
    """LLM or deterministic pattern summary — compose injection surface."""

    model_config = ConfigDict(extra="allow")

    source: SourceLabel | str = ""
    post_count: int = 0
    features: dict[str, Any] = Field(default_factory=dict)
    pattern_summary: str = ""
    winning_topics: list[str] = Field(default_factory=list)
    voice_signals: list[str] = Field(default_factory=list)
    recommended_constraints: list[str] = Field(default_factory=list)
    skipped: bool | None = None
    skip_reason: str | None = None
    errors: list[str] | None = None
    selected_winner_id: str | None = None  # set by brief_external_references step


@dataclass(frozen=True)
class ArtifactDef:
    key: ArtifactKey
    model: type[BaseModel]
    purpose: str
    producer: str = ""  # runbook step id for discoverability


ARTIFACTS: dict[ArtifactKey, ArtifactDef] = {
    ArtifactKey.ACCOUNT_BUNDLE: ArtifactDef(
        ArtifactKey.ACCOUNT_BUNDLE,
        AccountBundle,
        "X profile and tracked-post engagement metrics",
        "load_account_bundle",
    ),
    ArtifactKey.TIMELINE_REFERENCES: ArtifactDef(
        ArtifactKey.TIMELINE_REFERENCES,
        TimelineReferencesPayload,
        "External reference tweet pool for ranking",
        "fetch_timeline_references / merge_external_references",
    ),
    ArtifactKey.SEARCH_REFERENCES: ArtifactDef(
        ArtifactKey.SEARCH_REFERENCES,
        SearchReferencesPayload,
        "Search-sourced reference tweet pool",
        "fetch_search_references",
    ),
    ArtifactKey.OWN_POSTS: ArtifactDef(
        ArtifactKey.OWN_POSTS,
        OwnPostsPayload,
        "Own-post history with engagement metrics",
        "fetch_own_post_history",
    ),
    ArtifactKey.TIMELINE_RANKED: ArtifactDef(
        ArtifactKey.TIMELINE_RANKED,
        RankedReferencesPayload,
        "Top external references ranked by engagement",
        "rank_external_references",
    ),
    ArtifactKey.OWN_POSTS_RANKED: ArtifactDef(
        ArtifactKey.OWN_POSTS_RANKED,
        RankedReferencesPayload,
        "Top own posts ranked by engagement",
        "rank_own_posts",
    ),
    ArtifactKey.TIMELINE_ANALYSIS: ArtifactDef(
        ArtifactKey.TIMELINE_ANALYSIS,
        ReferencePatternBrief,
        "External reference pattern brief for compose",
        "brief_external_references",
    ),
    ArtifactKey.OWN_POSTS_ANALYSIS: ArtifactDef(
        ArtifactKey.OWN_POSTS_ANALYSIS,
        ReferencePatternBrief,
        "Own-post voice and success pattern brief",
        "brief_own_posts",
    ),
}

ARTIFACT_KEY_BY_CTX_KEY: dict[str, ArtifactKey] = {k.value: k for k in ArtifactKey}


def artifact_key_for_ctx_key(ctx_key: str) -> ArtifactKey | None:
    return ARTIFACT_KEY_BY_CTX_KEY.get(ctx_key)


# Minimal valid payloads for contract tests (task 8: test_artifacts.py)
CONTRACT_FIXTURES: dict[ArtifactKey, dict[str, Any]] = {
    ArtifactKey.ACCOUNT_BUNDLE: {
        "account_id": "acct_fixture",
        "profile": {"id": "99", "username": "fixture_user"},
        "tracked_tweet_ids": [],
        "post_engagements": [],
        "errors": [],
    },
    ArtifactKey.TIMELINE_REFERENCES: {
        "timeline_reference_tweets": [
            {"id": "t1", "text": "story https://example.com/a", "like_count": 1}
        ],
        "reference_errors": [],
    },
    ArtifactKey.SEARCH_REFERENCES: {
        "search_reference_tweets": [],
        "search_queries": ["news"],
        "per_query_counts": {},
        "reference_errors": [],
    },
    ArtifactKey.OWN_POSTS: {
        "account_id": "acct_fixture",
        "tweet_ids": ["p1"],
        "posts": [{"tweet_id": "p1", "post_text": "hello", "like_count": 5}],
    },
    ArtifactKey.TIMELINE_RANKED: {
        "ranked": [{"tweet_id": "t1", "text": "x", "metrics": {"like_count": 1}}],
        "winner": {"tweet_id": "t1", "text": "x", "metrics": {"like_count": 1}},
    },
    ArtifactKey.OWN_POSTS_RANKED: {"ranked": [], "winner": None},
    ArtifactKey.TIMELINE_ANALYSIS: {
        "source": "timeline",
        "post_count": 1,
        "pattern_summary": "fixture brief",
    },
    ArtifactKey.OWN_POSTS_ANALYSIS: {
        "source": "own_posts",
        "post_count": 0,
        "skipped": True,
        "skip_reason": "insufficient_own_posts",
    },
}
```

**Update `types/__init__.py`:**

```python
from app.pipeline.types.artifacts import (
    ARTIFACTS,
    ArtifactDef,
    ArtifactKey,
    AccountBundle,
    OwnPostsPayload,
    RankedReferencesPayload,
    ReferencePatternBrief,
    ReferenceTweetRow,
    SearchReferencesPayload,
    TimelineReferencesPayload,
)
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult, ToolKind, ToolRun, ToolSpec

__all__ = [
    "ARTIFACTS",
    "ArtifactDef",
    "ArtifactKey",
    "AccountBundle",
    "OwnPostsPayload",
    "RankedReferencesPayload",
    "ReferencePatternBrief",
    "ReferenceTweetRow",
    "SearchReferencesPayload",
    "StepResult",
    "TickRunContext",
    "TimelineReferencesPayload",
    "ToolKind",
    "ToolRun",
    "ToolSpec",
]
```

### d. Written explanation connecting changes to broader picture

`artifacts.py` turns the implicit context-key documentation into **executable contracts**. Once every write path calls `set_artifact`, invalid or drifted payloads fail fast at the producer instead of surfacing as `KeyError` or silent compose degradation downstream. The registry also feeds `Step.reads` / `Step.writes` (task 2) and optional mermaid graphs, so the runbook file becomes a **dataflow diagram**, not just an ordered function list. Keeping enum values identical to today's strings preserves `reference_phase.py`, ranked-ref selection, and compose injection without a coordinated migration.

---

## Section 3 – Decision Defense

### Chosen path: Pydantic models + central registry

| Alternative | Why not chosen |
|-------------|----------------|
| **TypedDict / Protocol only** | No runtime validation; does not satisfy locked “validate on every `set_artifact`”. |
| **Separate model per tool output** | Duplicates `TimelineReferencesPayload` vs tick-data dicts; registry centralizes one model per context key. |
| **Rename context keys to match step ids** | Breaks `reference_phase`, compose, and existing tests; explicitly out of scope. |
| **Full JSON Schema export** | Useful follow-up; registry + Pydantic is sufficient for Python pipeline. |

### `extra="allow"` on all payload models

X API and RavenDB documents evolve. Strict models would reject benign new fields and break production ticks. Required fields (`account_id`, list containers) catch structural mistakes; extras pass through for forward compatibility.

### `GatheredTweet` inside `RankedReferencesPayload`

Ranking already produces `GatheredTweet` instances (`reference_rank.rank_rows`). Reusing the type avoids a second normalization layer and keeps `ranked_refs_from_runbook` in `reference_phase.py` working via `GatheredTweet.model_validate(row)`.

### Contract fixtures in-module

Co-locating `CONTRACT_FIXTURES` with models keeps tests synchronized when fields change. Tests assert `ARTIFACTS[k].model.model_validate(CONTRACT_FIXTURES[k])` and separate invalid cases (missing `account_id`, wrong types).

### Frontend

**N/A** — backend-only typed context layer. Force-post SSE step IDs in `force_post_progress.py` remain separate from runbook step IDs (out of scope).

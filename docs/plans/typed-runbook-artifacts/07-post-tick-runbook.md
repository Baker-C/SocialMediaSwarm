# Task 7: post-tick-runbook

## Section 1 – Task Overview

### Goal

Rewrite `app/pipeline/runbooks/post_tick.py` to declare the reference runbook as a **`tuple[Step, ...]`** graph: parallel fetch block, merge, own-post fetch, parallel analyze block with **rank→brief chains**.

### Gathered context

Current runbook — flat seven-step tuple mixing steps and subagents:

```1:27:SocialMediaAutonomousAgents/backend/app/pipeline/runbooks/post_tick.py
"""Readable runbook: ordered steps for reference analysis before compose.

Each entry is ``(step_id, callable)``. Callables take ``(ctx, deps)`` only.
"""

from __future__ import annotations

from collections.abc import Callable

from app.pipeline.services import steps
from app.pipeline.subagents import own_posts, timeline
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

StepFn = Callable[[TickRunContext, PostRunDeps], StepResult]

# The runbook — read top to bottom; this is the source of truth for step order.
POST_TICK_REFERENCE_STEPS: tuple[tuple[str, StepFn], ...] = (
    ("profile", steps.profile),
    ("timeline_pool", steps.timeline_pool),
    ("search_pool", steps.search_pool),
    ("merge_reference_pools", steps.merge_reference_pools),
    ("own_posts_pool", steps.own_posts_pool),
    ("timeline_analysis", timeline.run),
    ("own_posts_analysis", own_posts.run),
)
```

Public re-export:

```41:42:SocialMediaAutonomousAgents/backend/app/pipeline/runbook.py
# Readable re-export of step order (for docs, tests, force-post UI alignment).
steps = POST_TICK_REFERENCE_STEPS
```

Tests assert old step names:

```22:32:SocialMediaAutonomousAgents/backend/tests/unit/test_pipeline_runbook.py
def test_runbook_step_names_are_readable() -> None:
    names = [name for name, _ in POST_TICK_REFERENCE_STEPS]
    assert names == [
        "profile",
        "timeline_pool",
        ...
    ]
```

### Target structure

```
load_account_bundle
parallel(fetch_timeline_references, fetch_search_references)     # id=fetch_external_references
merge_external_references
fetch_own_post_history
parallel(
  chain(rank_external_references, brief_external_references),  # id=external_reference_analysis
  chain(rank_own_posts, brief_own_posts),                    # id=own_posts_analysis
)                                                         # id=summarize_for_compose
```

### Dependencies

- Tasks 1–2 (ArtifactKey, Step, parallel, chain)
- Task 5 (step callables with new names)
- Task 6 (engine accepts `Sequence[Step]`)

### What it affects

- `runbook.steps` export type changes—consumers use `flatten_steps` for flat ID lists (task 8).
- `reference_phase.py` unchanged import path (`POST_TICK_REFERENCE_STEPS`).
- Pipeline outcome `phase` strings change prefix from `runbook:profile` to `runbook:load_account_bundle` (documented in task 8).

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

Replace tuple with declarative `Step` objects carrying `reads`/`writes` metadata. Use `parallel()` for fetch and analyze groups; use `chain()` inside analyze group so brief steps always follow rank steps. Remove direct subagent imports from runbook file.

### b. Before Panel

See full file citation in Section 1 (`post_tick.py` lines 1–27).

### c. After Panel

```python
"""Readable runbook: typed Step graph for reference analysis before compose.

Each leaf Step declares artifact reads/writes; parallel/chain composites structure the graph.
"""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.flow import Step, chain, parallel

# The runbook — read top to bottom; source of truth for step order AND dataflow.
POST_TICK_REFERENCE_STEPS: tuple[Step, ...] = (
    Step(
        id="load_account_bundle",
        run=steps.load_account_bundle,
        writes=(ArtifactKey.ACCOUNT_BUNDLE,),
        purpose="Load X profile and tracked-post engagement metrics",
    ),
    parallel(
        Step(
            id="fetch_timeline_references",
            run=steps.fetch_timeline_references,
            reads=(ArtifactKey.ACCOUNT_BUNDLE,),
            writes=(ArtifactKey.TIMELINE_REFERENCES,),
            purpose="Fetch following-timeline reference tweet pool",
        ),
        Step(
            id="fetch_search_references",
            run=steps.fetch_search_references,
            reads=(ArtifactKey.ACCOUNT_BUNDLE,),
            writes=(ArtifactKey.SEARCH_REFERENCES,),
            reads_optional=frozenset({ArtifactKey.SEARCH_REFERENCES}),
            purpose="Optional X recent-search reference pool (may skip)",
        ),
        id="fetch_external_references",
        purpose="Fetch timeline and optional search pools (parallel block)",
    ),
    Step(
        id="merge_external_references",
        run=steps.merge_external_references,
        reads=(ArtifactKey.TIMELINE_REFERENCES, ArtifactKey.SEARCH_REFERENCES),
        writes=(ArtifactKey.TIMELINE_REFERENCES,),
        reads_optional=frozenset({ArtifactKey.SEARCH_REFERENCES}),
        purpose="Merge search rows into timeline_references payload",
    ),
    Step(
        id="fetch_own_post_history",
        run=steps.fetch_own_post_history,
        writes=(ArtifactKey.OWN_POSTS,),
        reads_optional=frozenset({ArtifactKey.OWN_POSTS}),
        purpose="Load TrackedPost history from RavenDB",
    ),
    parallel(
        chain(
            Step(
                id="rank_external_references",
                run=steps.rank_external_references,
                reads=(ArtifactKey.TIMELINE_REFERENCES,),
                writes=(ArtifactKey.TIMELINE_RANKED, ArtifactKey.TIMELINE_ANALYSIS),
                reads_optional=frozenset({ArtifactKey.TIMELINE_RANKED}),
                purpose="Rank top external references; may write skip brief",
            ),
            Step(
                id="brief_external_references",
                run=steps.brief_external_references,
                reads=(ArtifactKey.TIMELINE_RANKED,),
                writes=(ArtifactKey.TIMELINE_ANALYSIS,),
                reads_optional=frozenset({ArtifactKey.TIMELINE_RANKED}),
                purpose="LLM pattern summary for external references",
            ),
            id="external_reference_analysis",
            purpose="Rank then brief external references",
        ),
        chain(
            Step(
                id="rank_own_posts",
                run=steps.rank_own_posts,
                reads=(ArtifactKey.OWN_POSTS,),
                writes=(ArtifactKey.OWN_POSTS_RANKED, ArtifactKey.OWN_POSTS_ANALYSIS),
                reads_optional=frozenset({ArtifactKey.OWN_POSTS, ArtifactKey.OWN_POSTS_RANKED}),
                purpose="Rank top own posts; may write skip brief",
            ),
            Step(
                id="brief_own_posts",
                run=steps.brief_own_posts,
                reads=(ArtifactKey.OWN_POSTS_RANKED,),
                writes=(ArtifactKey.OWN_POSTS_ANALYSIS,),
                reads_optional=frozenset({ArtifactKey.OWN_POSTS_RANKED}),
                purpose="LLM voice/success brief for own posts",
            ),
            id="own_posts_analysis",
            purpose="Rank then brief own posts",
        ),
        id="summarize_for_compose",
        purpose="Parallel external and own-post analysis branches",
    ),
)

# Convenience: flat leaf step IDs for tests and docs alignment
FLAT_REFERENCE_STEP_IDS: tuple[str, ...] = tuple(s.id for s in __import__(
    "app.pipeline.types.flow", fromlist=["flatten_steps"]
).flatten_steps(POST_TICK_REFERENCE_STEPS))
```

*(Optional: export `FLAT_REFERENCE_STEP_IDS` via `flatten_steps` at module load for tests.)*

### d. Written explanation connecting changes to broader picture

The runbook file becomes the **authoritative dataflow spec** operators read before debugging a tick. Parallel fetch documents independent I/O (timeline vs search) without implying async yet. Nested chains encode the locked rank→brief ordering inside each analysis branch. Removing subagent imports makes every runbook line a named step function in `steps.py`—subagents remain optional facades for package API stability.

---

## Section 3 – Decision Defense

### Chosen path: nested parallel + chain

| Alternative | Why not chosen |
|-------------|----------------|
| **Flat 11-step list** | Loses fetch/analyze grouping; harder to read. |
| **Parallel rank+brief** | Violates locked sequential rank→brief ordering. |
| **Keep subagents in runbook** | Hides four analysis steps from logs and docs. |

### `reads_optional` on search and skip-prone steps

Documents that `SEARCH_REFERENCES` / ranked artifacts may be absent when steps skip—engine does not enforce (validation on write still applies when artifacts are produced).

### Step ID churn vs context keys

Step IDs change (`profile` → `load_account_bundle`); **artifact key strings do not**—downstream dict reads stay stable.

### Frontend

**N/A** — backend runbook definition. Dashboard force-post SSE uses `FORCE_POST_STEP_ORDER` in `force_post_progress.py`, not runbook step IDs (alignment explicitly out of scope).

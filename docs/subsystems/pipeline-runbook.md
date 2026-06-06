# Pipeline runbook, tools, and subagents

Scope: the **`app/pipeline`** package — catalog of tools, analytic subagents, and the **runbook** that orders them for reference analysis before compose. Parent: [../PROJECT.md](../PROJECT.md).

This layer is being introduced alongside the existing tick in `interval/runner.py`. The **runbook** is the readable source of truth for step order; complexity stays in services, tools, and subagents.

## Design goals

| Goal | How |
|------|-----|
| Simple imports | `from app.pipeline import tools, runbook, subagents` |
| Obvious LLM vs non-LLM | Path: `tools/data/`, `tools/deterministic/`, `tools/llm/` |
| Readable execution order | `runbooks/post_tick.py` — tuple of `(step_id, callable)` |
| Hidden wiring | `services/steps.py`, `services/deps.py`, `_runbook_engine.py` |
| Expandable catalog | Register tools in `tools/_bootstrap.py`; add runbook lines |

## Quick start

```python
from app.pipeline import runbook

result = runbook.reference_analysis("JohnJames_News", niche="Broad News")
ctx = result.reference_context()
# ctx["timeline"], ctx["own_posts"], ranked payloads, pattern summaries
```

```python
from app.pipeline import tools

tools.data.timeline_fetch          # data tool (no LLM)
tools.deterministic.reference_rank
tools.llm.reference_pattern_summary  # LLM tool (has prompt_stem)
tools.llm.as_dict()                # all LLM tools by short name
```

## Package layout

```
backend/app/pipeline/
  __init__.py              # exports: tools, runbook, subagents, pipeline
  runbook.py               # public: start(), reference_analysis(), steps
  service.py               # PipelineService singleton + registry
  registry.py              # ToolSpec / SubagentSpec metadata
  accessors.py             # tool_catalog() for internal use (avoids import clash)
  _runbook_engine.py       # step loop (not public)
  types/
    context.py             # TickRunContext
    tool.py                # StepResult, ToolSpec
  services/
    deps.py                # PostRunDeps.build() — one deps bag per run
    steps.py               # thin wrappers: profile, timeline_pool, own_posts_pool
  tools/
    data/                  # I/O only — never LLM
    deterministic/         # score, rank, features — never LLM
    llm/                   # every Claude call + PROMPT_STEM
    _bootstrap.py          # registers all tools
    _catalog.py            # tools.data.* / .deterministic.* / .llm.*
  subagents/
    timeline.py            # external references: rank top 10 + pattern summary
    own_posts.py             # own TrackedPosts: rank top 10 + pattern summary
  runbooks/
    post_tick.py           # POST_TICK_REFERENCE_STEPS (ordered list)
```

**Note:** The directory `app/pipeline/tools/` (package) holds tool *implementations*. The lazy export `from app.pipeline import tools` resolves to the **ToolCatalog** (namespaces `.data`, `.deterministic`, `.llm`). Internal code uses `tool_catalog()` from `accessors.py` to avoid shadowing the package.

## Tool kinds

| Kind | Directory | LLM? | `TOOL_SOURCE` (optional) | Example |
|------|-----------|------|--------------------------|---------|
| **data** | `tools/data/` | No | `x_timeline`, `ravendb`, `x_api` | `timeline_fetch`, `own_posts_fetch` |
| **deterministic** | `tools/deterministic/` | No | — | `reference_rank`, `reference_score` |
| **llm** | `tools/llm/` | Yes | — | `reference_pattern_summary`, `compose_timeline_post` |

Each tool module exports:

- `TOOL_ID` — e.g. `data.timeline_fetch`
- `TOOL_KIND` — `data` | `deterministic` | `llm`
- `TOOL_PURPOSE` — human-readable
- `PROMPT_STEM` — **llm only** → `interval_crew/prompts/tasks/{stem}.*.md`
- `run(ctx, **kwargs) -> StepResult` — entry for runbook/services

### Registered tools (current)

| ID | Short name | Kind |
|----|------------|------|
| `data.account_profile` | `tools.data.account_profile` | data |
| `data.timeline_fetch` | `tools.data.timeline_fetch` | data |
| `data.own_posts_fetch` | `tools.data.own_posts_fetch` | data |
| `deterministic.reference_score` | `tools.deterministic.reference_score` | deterministic |
| `deterministic.reference_rank` | `tools.deterministic.reference_rank` | deterministic |
| `llm.compose_timeline_post` | `tools.llm.compose_timeline_post` | llm |
| `llm.reference_pattern_summary` | `tools.llm.reference_pattern_summary` | llm |

Add a tool: create module under the right folder + one row in `tools/_bootstrap.py`.

## Subagents

A **subagent** is a named analytic role with one public function:

```python
def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult
```

It orchestrates multiple tools internally. It is **not** an autonomous LLM router.

| Subagent | Module | Purpose | Uses LLM? |
|----------|--------|---------|-----------|
| Timeline reference analyst | `subagents/timeline.py` | Top external refs + pattern brief | Yes (`llm.reference_pattern_summary`) |
| Own-posts reference analyst | `subagents/own_posts.py` | Top own posts + voice/success brief | Yes (same LLM tool, `source=own_posts`) |

Import:

```python
from app.pipeline import subagents

subagents.timeline.run(ctx, deps)
subagents.own_posts.run(ctx, deps)
```

**Skip behavior:** own-posts analysis skips (does not fail the run) when fewer than 3 tracked posts or no registry. Timeline analysis skips when no URL-bearing references exist.

## Runbook

The runbook is the **only** place that defines step **order** for the reference-analysis phase.

File: `runbooks/post_tick.py`

```python
POST_TICK_REFERENCE_STEPS = (
    ("profile", steps.profile),
    ("timeline_pool", steps.timeline_pool),
    ("own_posts_pool", steps.own_posts_pool),
    ("timeline_analysis", timeline.run),
    ("own_posts_analysis", own_posts.run),
)
```

Public API (`runbook.py`):

| Function | Role |
|----------|------|
| `runbook.start(account_id, niche=..., mode=...)` | Create `TickRunContext` |
| `runbook.reference_analysis(account_id, ...)` | Run `POST_TICK_REFERENCE_STEPS` |
| `runbook.steps` | Re-export of step tuple (tests, force-post UI alignment) |

`PostRunDeps.build()` constructs `TickDataService`, repos, and Twitter once per run. Callers do not pass tick_data into the runbook.

Execution engine (`_runbook_engine.run_steps`) logs per-step `ok` / `skipped` / errors. Not imported by application code outside `pipeline/`.

## Relationship to `interval/runner.py`

Today the **production post tick** still flows through `Orchestrator` → `run_account_pipeline` in `interval/runner.py` (guards, slot claim, compose loop, publish).

The pipeline runbook implements the **reference analysis** slice (profile + pools + dual subagents) as a modular, documented path. Wiring the full tick to `runbook` (compose, safety, publish steps) is the next integration step.

| Layer | Today |
|-------|--------|
| Guards, slot, publish | `interval/runner.py` |
| Reference analysis runbook | `app/pipeline/runbooks/post_tick.py` |
| Compose (live) | `interval/compose_timeline_post.py` (also exposed as `tools.llm.compose_timeline_post`) |

## Prompt ↔ LLM tool mapping

| Prompt stem | LLM tool module |
|-------------|-----------------|
| `compose_timeline_post` | `tools/llm/compose_timeline_post.py` |
| `reference_pattern_summary` | `tools/llm/reference_pattern_summary.py` |

Files live under `backend/app/interval_crew/prompts/tasks/`. LLM tools load them via `prompt_loader` using `PROMPT_STEM`.

## Context keys (after reference runbook)

| Key | Set by |
|-----|--------|
| `account_bundle` | `steps.profile` |
| `timeline_references` | `steps.timeline_pool` |
| `own_posts` | `steps.own_posts_pool` |
| `timeline_ranked` | timeline subagent |
| `timeline_analysis` | timeline subagent |
| `own_posts_ranked` | own_posts subagent |
| `own_posts_analysis` | own_posts subagent |

`RunbookResult.reference_context()` returns a dict suitable for compose injection (future).

## Force post (dashboard / API)

Manual force post still enters via `Orchestrator.run_tick(mode="force")` or `POST /api/accounts/{id}/force-post` (SSE progress). Progress step IDs in `force_post_progress.py` should align with runbook step names as integration proceeds.

See [api-and-dashboard](api-and-dashboard.md) and [frontend-dashboard](frontend-dashboard.md).

## Adding a new capability

1. **Tool** — implement `run()` under `tools/{data|deterministic|llm}/`, register in `_bootstrap.py`.
2. **Subagent** (optional) — `subagents/foo.py` with `run(ctx, deps)` calling tools.
3. **Step wrapper** (if deps wiring is non-trivial) — one function in `services/steps.py`.
4. **Runbook** — add `(step_id, callable)` to `POST_TICK_REFERENCE_STEPS` or a new runbook tuple.
5. **Docs** — update this file and [interval-crew-llm](interval-crew-llm.md) if new prompts.

Do **not** import `_runbook_engine` or `_bootstrap` from outside `app/pipeline/`.

## Related docs

- Live tick gateway: [interval-orchestration](interval-orchestration.md)
- Timeline fetch (underlying data tool): [reference-ingestion](reference-ingestion.md)
- Compose + safety: [compose-and-safety](compose-and-safety.md)
- Prompt inventory: [interval-crew-llm](interval-crew-llm.md)
- TrackedPosts (own-posts pool): [persistence-ravendb](persistence-ravendb.md), [engagement-and-metrics](engagement-and-metrics.md)

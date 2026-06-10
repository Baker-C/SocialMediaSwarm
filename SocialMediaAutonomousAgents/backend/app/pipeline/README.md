# `app/pipeline`

Canonical detail: [`docs/subsystems/pipeline-runbook.md`](../../../../docs/subsystems/pipeline-runbook.md).

## Import surface

```python
from app.pipeline import tools, runbook, subagents

runbook.reference_analysis("account_id", niche="...")
tools.data.timeline_fetch
tools.llm.reference_pattern_summary
subagents.timeline.run(ctx, deps)
```

## Layout

- `tools/{data,deterministic,llm}/` — single-purpose capabilities
- `types/artifacts.py` — `ArtifactKey` + Pydantic models; `set_artifact` validates every write
- `types/flow.py` — `Step`, `parallel()`, `chain()` composites
- `subagents/` — thin wrappers delegating to rank/brief steps
- `services/` — `PostRunDeps.build()`, artifact-centric step functions
- `runbooks/post_tick.py` — typed runbook with parallel fetch + analyze chains
- `runbook.py` — public `reference_analysis()` entry

Do not import `_runbook_engine` or `_bootstrap` from outside this package.

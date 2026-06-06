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
- `subagents/` — `run(ctx, deps)` bundles (timeline + own-post analysts)
- `services/` — `PostRunDeps.build()`, step wrappers (hidden wiring)
- `runbooks/post_tick.py` — ordered step list (readable)
- `runbook.py` — public `reference_analysis()` entry

Do not import `_runbook_engine` or `_bootstrap` from outside this package.

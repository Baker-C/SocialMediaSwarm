"""Post pipeline — simple surface, complexity behind services.

Quick start::

    from app.pipeline import tools, runbook, subagents

    # Tools by kind
    tools.data.timeline_fetch
    tools.llm.reference_pattern_summary

    # Runbook (ordered steps, deps hidden)
    result = runbook.reference_analysis(\"acct1\", niche=\"News\")
    result.reference_context()

    # Subagents (used by runbook; callable directly if needed)
    subagents.timeline.run(ctx, deps)
"""

from __future__ import annotations

from app.pipeline._lazy import _LazyAttr
from app.pipeline import runbook
from app.pipeline import subagents
from app.pipeline.service import PipelineService, get_pipeline, reset_pipeline


tools = _LazyAttr(lambda: get_pipeline().tools)
pipeline = _LazyAttr(get_pipeline)

__all__ = [
    "PipelineService",
    "get_pipeline",
    "pipeline",
    "reset_pipeline",
    "runbook",
    "subagents",
    "tools",
]

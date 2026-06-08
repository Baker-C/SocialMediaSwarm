"""Register all pipeline tools into the registry."""

from __future__ import annotations

from app.pipeline.registry import PipelineRegistry
from app.pipeline.tools._tool_module import register_tool_module

_TOOL_DEFINITIONS: list[dict] = [
    {
        "id": "data.account_profile",
        "kind": "data",
        "name": "account_profile",
        "purpose": "Load X profile and tracked-post engagement metrics",
        "module": "app.pipeline.tools.data.account_profile",
        "source": "x_api",
    },
    {
        "id": "data.timeline_fetch",
        "kind": "data",
        "name": "timeline_fetch",
        "purpose": "Acquire external timeline reference tweet pool",
        "module": "app.pipeline.tools.data.timeline_fetch",
        "source": "x_timeline",
    },
    {
        "id": "data.search_fetch",
        "kind": "data",
        "name": "search_fetch",
        "purpose": "Acquire reference tweets from X recent-search queries",
        "module": "app.pipeline.tools.data.search_fetch",
        "source": "x_search",
    },
    {
        "id": "data.own_posts_fetch",
        "kind": "data",
        "name": "own_posts_fetch",
        "purpose": "Acquire own-post history with engagement metrics",
        "module": "app.pipeline.tools.data.own_posts_fetch",
        "source": "ravendb",
    },
    {
        "id": "deterministic.reference_score",
        "kind": "deterministic",
        "name": "reference_score",
        "purpose": "Compute weighted engagement score for metrics rows",
        "module": "app.pipeline.tools.deterministic.reference_score",
    },
    {
        "id": "deterministic.reference_rank",
        "kind": "deterministic",
        "name": "reference_rank",
        "purpose": "Rank reference rows and select top performers",
        "module": "app.pipeline.tools.deterministic.reference_rank",
    },
    {
        "id": "llm.compose_timeline_post",
        "kind": "llm",
        "name": "compose_timeline_post",
        "purpose": "Generate opinion + quip post body from a reference tweet",
        "module": "app.pipeline.tools.llm.compose_timeline_post",
        "prompt_stem": "compose_timeline_post",
    },
    {
        "id": "llm.reference_pattern_summary",
        "kind": "llm",
        "name": "reference_pattern_summary",
        "purpose": "Summarize success patterns across top reference posts",
        "module": "app.pipeline.tools.llm.reference_pattern_summary",
        "prompt_stem": "reference_pattern_summary",
    },
]


def bootstrap_tools(registry: PipelineRegistry) -> None:
    for row in _TOOL_DEFINITIONS:
        register_tool_module(registry, **row)

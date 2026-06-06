"""Central pipeline service: registry, tools, subagents, runbooks."""

from __future__ import annotations

from app.pipeline.registry import PipelineRegistry, SubagentSpec
from app.pipeline.tools._bootstrap import bootstrap_tools
from app.pipeline.tools._catalog import ToolCatalog


class PipelineService:
    """Single entry point for importing and resolving pipeline capabilities."""

    def __init__(self, registry: PipelineRegistry | None = None) -> None:
        self.registry = registry or PipelineRegistry()
        if not self.registry.tool_ids():
            bootstrap_tools(self.registry)
        self._tools = ToolCatalog(self.registry)

    @property
    def tools(self) -> ToolCatalog:
        return self._tools

    def register_subagent(self, spec: SubagentSpec) -> None:
        self.registry.register_subagent(spec)


_default_service: PipelineService | None = None


def get_pipeline() -> PipelineService:
    """Return the process-wide pipeline service singleton."""
    global _default_service
    if _default_service is None:
        _default_service = PipelineService()
    return _default_service


def reset_pipeline() -> None:
    """Clear the singleton (tests only)."""
    global _default_service
    _default_service = None

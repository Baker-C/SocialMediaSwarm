"""Central registry of pipeline tools."""

from __future__ import annotations

from typing import Literal

from app.pipeline.types.tool import ToolKind, ToolSpec

KindFilter = ToolKind | Literal["all"]


class PipelineRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.id in self._tools:
            raise ValueError(f"Duplicate tool id: {spec.id}")
        self._tools[spec.id] = spec

    def tool(self, tool_id: str) -> ToolSpec:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {tool_id}") from exc

    def tools(self, *, kind: KindFilter = "all") -> list[ToolSpec]:
        rows = list(self._tools.values())
        if kind == "all":
            return sorted(rows, key=lambda t: t.id)
        return sorted([t for t in rows if t.kind == kind], key=lambda t: t.id)

    def tool_ids(self, *, kind: KindFilter = "all") -> list[str]:
        return [t.id for t in self.tools(kind=kind)]

"""Central registry of pipeline tools and subagents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.pipeline.types.tool import ToolKind, ToolSpec

KindFilter = ToolKind | Literal["all"]


@dataclass(frozen=True)
class SubagentSpec:
    id: str
    name: str
    purpose: str
    module: str
    tools: tuple[str, ...]
    prompts: tuple[str, ...] = ()
    output_type: str = ""


class PipelineRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._subagents: dict[str, SubagentSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.id in self._tools:
            raise ValueError(f"Duplicate tool id: {spec.id}")
        self._tools[spec.id] = spec

    def register_subagent(self, spec: SubagentSpec) -> None:
        if spec.id in self._subagents:
            raise ValueError(f"Duplicate subagent id: {spec.id}")
        self._subagents[spec.id] = spec

    def tool(self, tool_id: str) -> ToolSpec:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {tool_id}") from exc

    def subagent(self, subagent_id: str) -> SubagentSpec:
        try:
            return self._subagents[subagent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown subagent: {subagent_id}") from exc

    def tools(self, *, kind: KindFilter = "all") -> list[ToolSpec]:
        rows = list(self._tools.values())
        if kind == "all":
            return sorted(rows, key=lambda t: t.id)
        return sorted([t for t in rows if t.kind == kind], key=lambda t: t.id)

    def subagents(self) -> list[SubagentSpec]:
        return sorted(self._subagents.values(), key=lambda s: s.id)

    def tool_ids(self, *, kind: KindFilter = "all") -> list[str]:
        return [t.id for t in self.tools(kind=kind)]

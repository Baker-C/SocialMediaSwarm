"""Attribute and mapping access to a group of tools (data / deterministic / llm)."""

from __future__ import annotations

from typing import Iterator

from app.pipeline.tools._tool_module import ToolModule
from app.pipeline.types.tool import ToolKind


class ToolNamespace:
    """Exposes tools as attributes, mappings, and iterables."""

    def __init__(self, kind: ToolKind, tools: dict[str, ToolModule]) -> None:
        self.kind = kind
        self._tools = dict(tools)

    def get(self, name: str) -> ToolModule:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"No {self.kind} tool named {name!r}") from exc

    def __getattr__(self, name: str) -> ToolModule:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)

    def __getitem__(self, name: str) -> ToolModule:
        return self.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._tools))

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def ids(self) -> list[str]:
        return [t.id for t in self.all()]

    def all(self) -> list[ToolModule]:
        return [self._tools[k] for k in sorted(self._tools)]

    def as_dict(self) -> dict[str, ToolModule]:
        return dict(self._tools)

    def __repr__(self) -> str:
        return f"<ToolNamespace {self.kind} {self.names()}>"

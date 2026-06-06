"""Build attribute namespaces: tools.data.*, tools.deterministic.*, tools.llm.*."""

from __future__ import annotations

from app.pipeline.registry import PipelineRegistry
from app.pipeline.tools._namespace import ToolNamespace
from app.pipeline.tools._tool_module import ToolModule, load_tool_module
from app.pipeline.types.tool import ToolKind


class ToolCatalog:
    """Central import surface for pipeline tools."""

    def __init__(self, registry: PipelineRegistry) -> None:
        self._registry = registry
        self._loaded: dict[str, ToolModule] = {}
        self._namespaces: dict[ToolKind, ToolNamespace] | None = None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        for spec in self._registry.tools():
            self._loaded[spec.id] = load_tool_module(spec)
        grouped: dict[ToolKind, dict[str, ToolModule]] = {
            "data": {},
            "deterministic": {},
            "llm": {},
        }
        for tool_id, module in self._loaded.items():
            kind = module.kind
            grouped[kind][module.name] = module
        self._namespaces = {
            kind: ToolNamespace(kind, tools) for kind, tools in grouped.items()
        }

    @property
    def data(self) -> ToolNamespace:
        self._ensure_loaded()
        assert self._namespaces is not None
        return self._namespaces["data"]

    @property
    def deterministic(self) -> ToolNamespace:
        self._ensure_loaded()
        assert self._namespaces is not None
        return self._namespaces["deterministic"]

    @property
    def llm(self) -> ToolNamespace:
        self._ensure_loaded()
        assert self._namespaces is not None
        return self._namespaces["llm"]

    def get(self, tool_id: str) -> ToolModule:
        self._ensure_loaded()
        try:
            return self._loaded[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool id: {tool_id}") from exc

    def by_kind(self, kind: ToolKind) -> ToolNamespace:
        if kind == "data":
            return self.data
        if kind == "deterministic":
            return self.deterministic
        return self.llm

    def all(self) -> list[ToolModule]:
        self._ensure_loaded()
        return [self._loaded[k] for k in sorted(self._loaded)]

    def ids(self) -> list[str]:
        return self._registry.tool_ids()

    def llm_tools(self) -> dict[str, ToolModule]:
        return self.llm.as_dict()

    def data_tools(self) -> dict[str, ToolModule]:
        return self.data.as_dict()

    def deterministic_tools(self) -> dict[str, ToolModule]:
        return self.deterministic.as_dict()

    def __repr__(self) -> str:
        return f"<ToolCatalog data={len(self.data)} deterministic={len(self.deterministic)} llm={len(self.llm)}>"

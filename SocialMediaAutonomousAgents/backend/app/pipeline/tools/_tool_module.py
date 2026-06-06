"""Wrapper exposing a tool module through the pipeline catalog."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from app.pipeline.registry import PipelineRegistry
from app.pipeline.types.tool import ToolKind, ToolRun, ToolSpec


class ToolModule:
    """One registered tool: metadata + the underlying implementation module."""

    def __init__(self, spec: ToolSpec, module: ModuleType) -> None:
        self.spec = spec
        self._module = module

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def kind(self) -> ToolKind:
        return self.spec.kind

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def purpose(self) -> str:
        return self.spec.purpose

    @property
    def source(self) -> str | None:
        return self.spec.source

    @property
    def prompt_stem(self) -> str | None:
        return self.spec.prompt_stem

    @property
    def run(self) -> ToolRun:
        fn = getattr(self._module, "run", None)
        if fn is None:
            raise AttributeError(f"Tool {self.id} has no run() function")
        return fn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)

    def __repr__(self) -> str:
        return f"<ToolModule {self.id} kind={self.kind}>"


def load_tool_module(spec: ToolSpec) -> ToolModule:
    module = importlib.import_module(spec.module)
    return ToolModule(spec, module)


def register_tool_module(
    registry: PipelineRegistry,
    *,
    id: str,
    kind: ToolKind,
    name: str,
    purpose: str,
    module: str,
    source: str | None = None,
    prompt_stem: str | None = None,
) -> ToolSpec:
    spec = ToolSpec(
        id=id,
        kind=kind,
        name=name,
        purpose=purpose,
        module=module,
        source=source,
        prompt_stem=prompt_stem,
    )
    registry.register_tool(spec)
    return spec

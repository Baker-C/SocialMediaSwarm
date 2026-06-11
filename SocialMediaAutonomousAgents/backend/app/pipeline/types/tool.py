"""Contracts for pipeline tools and step results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolKind = Literal["data", "deterministic", "llm"]


@dataclass(frozen=True)
class ToolSpec:
    id: str
    kind: ToolKind
    name: str
    purpose: str
    module: str
    source: str | None = None
    prompt_stem: str | None = None


@dataclass
class StepResult:
    ok: bool = True
    skipped: bool = False
    skip_reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


ToolRun = Callable[..., StepResult | dict[str, Any] | Any]

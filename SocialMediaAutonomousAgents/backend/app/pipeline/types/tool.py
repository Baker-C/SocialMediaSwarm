"""Contracts for pipeline step results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    ok: bool = True
    skipped: bool = False
    skip_reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

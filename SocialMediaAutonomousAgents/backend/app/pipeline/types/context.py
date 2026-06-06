"""Mutable run context passed through the post runbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TickMode = Literal["scheduled", "force"]


@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

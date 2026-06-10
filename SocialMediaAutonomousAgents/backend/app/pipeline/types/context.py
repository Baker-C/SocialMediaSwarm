"""Mutable run context passed through the post runbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.pipeline.types.artifacts import ARTIFACTS, ArtifactKey

TickMode = Literal["scheduled", "force"]


@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Low-level write; prefer set_artifact in pipeline code."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def get_artifact(self, key: ArtifactKey) -> BaseModel | None:
        raw = self.data.get(key.value)
        if raw is None:
            return None
        model = ARTIFACTS[key].model
        if isinstance(raw, model):
            return raw
        return model.model_validate(raw)

    def require_artifact(self, key: ArtifactKey) -> BaseModel:
        artifact = self.get_artifact(key)
        if artifact is None:
            raise KeyError(f"Required artifact missing: {key.value}")
        return artifact

    def set_artifact(self, key: ArtifactKey, value: BaseModel | dict[str, Any]) -> None:
        """Validate and store an artifact; all pipeline writes must use this."""
        model = ARTIFACTS[key].model
        try:
            validated = model.model_validate(value)
        except ValidationError as exc:
            raise ValueError(f"Invalid artifact {key.value}: {exc}") from exc
        self.data[key.value] = validated.model_dump(mode="json")

    def has_artifact(self, key: ArtifactKey) -> bool:
        return key.value in self.data and self.data[key.value] is not None

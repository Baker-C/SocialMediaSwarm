"""Shared contracts between orchestration and interval_crew runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TickMode = Literal["scheduled", "force"]


class TickInput(BaseModel):
    account_id: str
    niche: str
    slot: str
    mode: TickMode = "scheduled"
    account_system_prompt: str = ""
    account_personality: str = ""
    negative_semantics: list[str] = Field(default_factory=list)
    max_candidates: int = 5


class TickBrief(BaseModel):
    account_bundle: dict[str, Any] = Field(default_factory=dict)
    niche_bundle: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    topic_preanalysis: dict[str, Any] = Field(default_factory=dict)
    prompt_bundle: str = ""


class TickOutput(BaseModel):
    candidates: list[str] = Field(default_factory=list)
    prompt_bundle: str = ""
    brief: TickBrief | None = None
    errors: list[str] = Field(default_factory=list)

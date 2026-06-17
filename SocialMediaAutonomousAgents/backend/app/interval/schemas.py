"""Shared contracts for the interval orchestration tick."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TickMode = Literal["scheduled", "force"]


class TickInput(BaseModel):
    account_id: str
    niche: str
    slot: str
    mode: TickMode = "scheduled"
    account_personality: str = ""
    max_candidates: int = 5

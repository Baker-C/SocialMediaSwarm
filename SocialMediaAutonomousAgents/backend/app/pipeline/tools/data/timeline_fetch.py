"""Fetch following-timeline reference tweets (non-own posts)."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService

TOOL_ID = "data.timeline_fetch"
TOOL_KIND = "data"
TOOL_SOURCE = "x_timeline"
TOOL_PURPOSE = "Acquire external timeline reference tweet pool"


def run(
    ctx: TickRunContext,
    *,
    tick_data: TickDataService,
    authenticated_user_id: str | None = None,
    account_id: str | None = None,
    slot: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    slot_key = (slot or ctx.slot).strip()
    payload = tick_data.compile_timeline_reference_tweets(
        aid,
        authenticated_user_id=authenticated_user_id,
        slot=slot_key,
    )
    ctx.set("timeline_references", payload)
    return StepResult(ok=True, payload={"timeline_references": payload})


def fetch(
    tick_data: TickDataService,
    account_id: str,
    *,
    authenticated_user_id: str | None,
    slot: str,
) -> dict[str, Any]:
    return tick_data.compile_timeline_reference_tweets(
        account_id,
        authenticated_user_id=authenticated_user_id,
        slot=slot,
    )

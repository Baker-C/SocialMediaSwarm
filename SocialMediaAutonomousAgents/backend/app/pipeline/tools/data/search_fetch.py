"""Fetch X recent-search reference tweets for one or more query strings."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService

TOOL_ID = "data.search_fetch"
TOOL_KIND = "data"
TOOL_SOURCE = "x_search"
TOOL_PURPOSE = "Acquire reference tweets from X recent-search queries"


def run(
    ctx: TickRunContext,
    *,
    tick_data: TickDataService,
    queries: list[str],
    authenticated_user_id: str | None = None,
    account_id: str | None = None,
    slot: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    slot_key = (slot or ctx.slot).strip()
    payload = tick_data.compile_search_reference_tweets(
        aid,
        queries=queries,
        slot=slot_key,
        authenticated_user_id=authenticated_user_id,
    )
    ctx.set("search_references", payload)
    return StepResult(ok=True, payload={"search_references": payload})


def fetch(
    tick_data: TickDataService,
    account_id: str,
    *,
    queries: list[str],
    authenticated_user_id: str | None,
    slot: str,
) -> dict[str, Any]:
    return tick_data.compile_search_reference_tweets(
        account_id,
        queries=queries,
        slot=slot,
        authenticated_user_id=authenticated_user_id,
    )

"""Fetch account profile and tracked-post engagement metrics."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.tick_data_service import TickDataService

TOOL_ID = "data.account_profile"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Load X profile and tracked-post engagement metrics for an account"


def run(
    ctx: TickRunContext,
    *,
    tick_data: TickDataService,
    account_id: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    bundle = tick_data.compile_account_bundle(aid)
    ctx.set("account_bundle", bundle)
    return StepResult(ok=True, payload={"account_bundle": bundle})


def fetch(tick_data: TickDataService, account_id: str) -> dict[str, Any]:
    """Direct helper for callers that do not use TickRunContext yet."""
    return tick_data.compile_account_bundle(account_id)

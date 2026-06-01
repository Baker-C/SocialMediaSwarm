"""CrewAI tool: account profile bundle."""

from __future__ import annotations

import json
from typing import Any

from app.services.tick_data_service import TickDataService


def fetch_account_bundle(tick_data: TickDataService, account_id: str) -> str:
    bundle = tick_data.compile_account_bundle(account_id)
    return json.dumps(bundle, default=str)


def make_x_profile_tool(tick_data: TickDataService) -> Any:
    try:
        from crewai.tools import tool
    except ImportError:
        return None

    @tool("fetch_x_account_bundle")
    def _tool(account_id: str) -> str:
        """Fetch X profile and tracked-post engagement metrics for an account."""
        return fetch_account_bundle(tick_data, account_id)

    return _tool

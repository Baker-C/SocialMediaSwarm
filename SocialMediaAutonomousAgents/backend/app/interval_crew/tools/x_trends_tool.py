"""CrewAI tool: niche trends / discourse snapshot."""

from __future__ import annotations

import json
from typing import Any

from app.services.tick_data_service import TickDataService


def fetch_niche_discourse(tick_data: TickDataService, account_id: str, niche: str) -> str:
    bundle = tick_data.compile_niche_discourse(account_id, niche)
    return json.dumps(bundle, default=str)


def make_x_trends_tool(tick_data: TickDataService) -> Any:
    try:
        from crewai.tools import tool
    except ImportError:
        return None

    @tool("fetch_x_trends_discourse")
    def _tool(account_id: str, niche: str) -> str:
        """Fetch global trends snapshot and niche discourse summary."""
        return fetch_niche_discourse(tick_data, account_id, niche)

    return _tool

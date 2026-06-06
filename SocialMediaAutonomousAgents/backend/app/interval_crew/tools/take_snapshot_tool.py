"""CrewAI tool: collect and persist a point-in-time account snapshot."""

from __future__ import annotations

import json
from typing import Any

from app.models.account_snapshot import AccountSnapshotDocument
from app.services.account_repository import AccountRepository
from app.services.account_snapshot_repository import AccountSnapshotRepository
from app.services.account_snapshot_service import create_account_snapshot
from app.services.post_registry import TrackedPostRepository


def take_snapshot(
    account_id: str,
    *,
    refresh_from_x: bool = False,
    repo: AccountRepository | None = None,
    post_registry: TrackedPostRepository | None = None,
    snapshots: AccountSnapshotRepository | None = None,
) -> AccountSnapshotDocument:
    """Collect profile, voice, and engagement data for an account and save a snapshot to the DB.

    Raises ``LookupError`` if the account does not exist.
    """
    return create_account_snapshot(
        account_id,
        refresh_from_x=refresh_from_x,
        repo=repo,
        tracked=post_registry,
        snapshots=snapshots,
    )


def make_take_snapshot_tool(
    repo: AccountRepository | None = None,
    post_registry: TrackedPostRepository | None = None,
) -> Any:
    try:
        from crewai.tools import tool
    except ImportError:
        return None

    @tool("take_account_snapshot")
    def _tool(account_id: str) -> str:
        """Capture and persist a snapshot of an account's profile, voice, and engagement totals."""
        snap = take_snapshot(account_id, repo=repo, post_registry=post_registry)
        return json.dumps(snap.model_dump(exclude_none=True), default=str)

    return _tool

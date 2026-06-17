"""Collect and persist a point-in-time account snapshot."""

from __future__ import annotations

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

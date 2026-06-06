"""Build and persist point-in-time account snapshots."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.account_snapshot import AccountSnapshotDocument
from app.services.account_repository import AccountRepository
from app.services.account_snapshot_repository import AccountSnapshotRepository
from app.services.post_registry import TrackedPostRepository

logger = logging.getLogger(__name__)


def create_account_snapshot(
    account_id: str,
    *,
    refresh_from_x: bool = False,
    repo: AccountRepository | None = None,
    tracked: TrackedPostRepository | None = None,
    snapshots: AccountSnapshotRepository | None = None,
) -> AccountSnapshotDocument:
    """Capture an account's current profile/voice/engagement state as a snapshot.

    Raises ``LookupError`` if the account does not exist.
    """
    account_repo = repo or AccountRepository()
    tracked_repo = tracked or TrackedPostRepository()
    snapshot_repo = snapshots or AccountSnapshotRepository()

    acc = account_repo.load(account_id)
    if acc is None:
        raise LookupError(f"Unknown account_id={account_id}")

    followers = acc.followers
    following_count = 0
    posts_total = acc.posts_total

    if refresh_from_x:
        try:
            from app.services.twitter_service import TwitterService

            data = TwitterService(account_repo).get_account_data(account_id)
            if isinstance(data.get("followers_count"), int):
                followers = data["followers_count"]
            if isinstance(data.get("following_count"), int):
                following_count = data["following_count"]
            if isinstance(data.get("tweet_count"), int):
                posts_total = data["tweet_count"]
        except Exception as exc:
            logger.warning(
                "account snapshot X refresh failed account_id=%s: %s", account_id, exc
            )

    total_likes, total_views = tracked_repo.totals_for_account(account_id)

    snapshot = AccountSnapshotDocument(
        account_id=acc.account_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        niche=acc.niche,
        twitter_handle=acc.twitter_handle,
        followers=followers,
        following_count=following_count,
        posts_total=posts_total,
        total_likes=total_likes,
        total_views=total_views,
        system_prompt=acc.system_prompt,
        personality=acc.personality,
        negative_semantics=list(acc.negative_semantics),
    )
    snapshot_repo.save(snapshot)
    logger.info("account snapshot created account_id=%s", account_id)
    return snapshot

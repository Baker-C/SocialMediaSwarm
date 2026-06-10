"""Load tracked own-post rows and metrics from RavenDB."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.artifacts import ArtifactKey, OwnPostsPayload
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.post_registry import TrackedPostRepository

TOOL_ID = "data.own_posts_fetch"
TOOL_KIND = "data"
TOOL_SOURCE = "ravendb"
TOOL_PURPOSE = "Acquire own-post history with engagement metrics for performance analysis"
TOOL_WRITES = (ArtifactKey.OWN_POSTS,)
OUTPUT_MODEL = OwnPostsPayload


def run(
    ctx: TickRunContext,
    *,
    post_registry: TrackedPostRepository,
    account_id: str | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    rows = post_registry.list_for_account(aid)
    tweet_ids = post_registry.list_tweet_ids(aid)
    payload = {"account_id": aid, "tweet_ids": tweet_ids, "posts": rows}
    ctx.set_artifact(ArtifactKey.OWN_POSTS, payload)
    return StepResult(ok=True, payload=payload)


def fetch(post_registry: TrackedPostRepository, account_id: str) -> dict[str, Any]:
    rows = post_registry.list_for_account(account_id)
    return {
        "account_id": account_id,
        "tweet_ids": post_registry.list_tweet_ids(account_id),
        "posts": rows,
    }

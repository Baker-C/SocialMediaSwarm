"""Fetch recent published posts per account for performance analysis."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.post_registry import TrackedPostRepository

TOOL_ID = "data.fetch_recent_posts"
TOOL_KIND = "data"
TOOL_PURPOSE = "Fetch recent published posts per account for performance analysis"
TOOL_READS = ["all_accounts"]
TOOL_WRITES = ["recent_posts"]


def run(
    ctx: TickRunContext,
    *,
    post_registry: TrackedPostRepository | None = None,
    limit: int = 20,
) -> StepResult:
    all_accounts: list[dict[str, Any]] = ctx.get("all_accounts") or []
    result = fetch(all_accounts=all_accounts, post_registry=post_registry, limit=limit)
    ctx.set("recent_posts", result)
    total = sum(len(posts) for posts in result.values())
    return StepResult(ok=True, payload={"account_count": len(result), "total_posts": total})


def fetch(
    *,
    all_accounts: list[dict[str, Any]],
    post_registry: TrackedPostRepository | None = None,
    limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Return {account_id: [post_dict, ...]} for each account."""
    registry = post_registry or TrackedPostRepository()
    cap = max(1, int(limit))
    result: dict[str, list[dict[str, Any]]] = {}
    for account in all_accounts:
        account_id = account.get("account_id")
        if not account_id:
            continue
        rows = registry.list_for_account(account_id, limit=cap)
        result[account_id] = [_normalize_post(r, account_id) for r in rows]
    return result


def _normalize_post(row: dict[str, Any], account_id: str) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "post_id": row.get("post_id") or row.get("tweet_id") or row.get("id"),
        "tweet_id": row.get("tweet_id") or row.get("post_id") or row.get("id"),
        "text": str(row.get("text") or ""),
        "pipeline_id": row.get("pipeline_id"),
        "pipeline_weight_at_post": row.get("pipeline_weight_at_post"),
        "views": int(row.get("views") or row.get("impression_count") or 0),
        "likes": int(row.get("likes") or row.get("like_count") or 0),
        "created_at": row.get("created_at") or row.get("posted_at"),
    }

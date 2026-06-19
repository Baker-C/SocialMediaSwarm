"""LLM semantic classification of posts against account niche lists."""

from __future__ import annotations

import json
from typing import Any

from app.infrastructure.claude_client import get_claude_client
from app.interval_crew import prompt_loader
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.classify_posts_by_niche"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Semantically match each post to the account's niche list"
TOOL_READS = ["recent_posts", "all_accounts"]
TOOL_WRITES = ["posts_with_niche"]
PROMPT_STEM = "classify_posts_by_niche"


def run(
    ctx: TickRunContext,
    *,
    all_accounts: list[dict[str, Any]],
    recent_posts: dict[str, list[dict[str, Any]]],
) -> StepResult:
    """Classify posts per account by niche, write results to ctx.data['posts_with_niche']."""
    posts_with_niche: dict[str, list[dict[str, Any]]] = {}
    for account in all_accounts:
        account_id = str(account.get("id") or account.get("account_id") or "")
        if not account_id:
            continue
        soul = account.get("soul") or {}
        niches = soul.get("niches") or []
        posts = recent_posts.get(account_id) or []
        posts_with_niche[account_id] = classify_account_posts(
            posts=posts,
            niches=niches,
        )
    ctx.set("posts_with_niche", posts_with_niche)
    return StepResult(ok=True, payload={"account_count": len(posts_with_niche)})


def classify_account_posts(
    *,
    posts: list[dict[str, Any]],
    niches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return posts annotated with a 'niche_id' field."""
    if not posts:
        return []
    if not niches:
        for post in posts:
            post = dict(post)
            post["niche_id"] = None
        return [dict(p) | {"niche_id": None} for p in posts]

    claude = get_claude_client()
    annotated = [dict(p) for p in posts]

    if not claude.enabled:
        for post in annotated:
            post["niche_id"] = niches[0].get("name") if niches else None
        return annotated

    system = _load_prompt("system")
    user = _load_prompt("user").format(
        niches_json=json.dumps(_trim_niches(niches), indent=2, default=str),
        posts_json=json.dumps(_trim_posts(posts), indent=2, default=str),
        post_count=len(posts),
    )
    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
    except Exception:
        return annotated

    if not isinstance(data, list):
        return annotated

    index_to_niche: dict[int, str] = {}
    for item in data:
        if isinstance(item, dict):
            idx = item.get("post_index")
            niche_id = item.get("niche_id")
            if isinstance(idx, int) and niche_id is not None:
                index_to_niche[idx] = str(niche_id)

    for i, post in enumerate(annotated):
        post["niche_id"] = index_to_niche.get(i)

    return annotated


def _load_prompt(suffix: str) -> str:
    path = f"tasks/{PROMPT_STEM}.{suffix}.md"
    try:
        return prompt_loader.load(path)
    except FileNotFoundError:
        if suffix == "system":
            return (
                "You are a content classifier. Given a list of niches and a list of posts, "
                "match each post to the most relevant niche. "
                "Return a JSON array: [{\"post_index\": int, \"niche_id\": str}] "
                "where niche_id is the niche name."
            )
        return (
            "Niches:\n{niches_json}\n\n"
            "Posts ({post_count} total):\n{posts_json}\n\n"
            "For each post, return the niche_id (use niche name as id) that best matches. "
            "Return JSON array: [{\"post_index\": int, \"niche_id\": str}]"
        )


def _trim_niches(niches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for n in niches:
        if not isinstance(n, dict):
            continue
        out.append({
            "name": n.get("name"),
            "description": str(n.get("description") or "")[:200],
            "score": n.get("score"),
        })
    return out


def _trim_posts(posts: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    out = []
    for i, row in enumerate(posts[:limit]):
        if not isinstance(row, dict):
            continue
        out.append({
            "post_index": i,
            "tweet_id": row.get("tweet_id") or row.get("id"),
            "text": str(row.get("text") or "")[:400],
        })
    return out

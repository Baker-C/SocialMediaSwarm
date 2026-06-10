"""LLM analysis of common patterns across top-performing reference posts."""

from __future__ import annotations

import json
from typing import Any, Literal

from app.infrastructure.claude_client import get_claude_client
from app.interval_crew import prompt_loader
from app.pipeline.types.artifacts import ReferencePatternBrief, artifact_key_for_ctx_key
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.reference_pattern_summary"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Summarize language, topic, and success patterns across top reference posts"
PROMPT_STEM = "reference_pattern_summary"
OUTPUT_MODEL = ReferencePatternBrief

SourceLabel = Literal["timeline", "own_posts"]


def run(
    ctx: TickRunContext,
    *,
    source: SourceLabel,
    niche: str,
    top_posts: list[dict[str, Any]],
    features: dict[str, Any] | None = None,
    store_key: str | None = None,
) -> StepResult:
    summary = summarize(source=source, niche=niche, top_posts=top_posts, features=features or {})
    key = store_key or f"{source}_pattern_summary"
    artifact_key = artifact_key_for_ctx_key(key)
    if artifact_key is None:
        raise ValueError(f"Unknown analysis artifact store_key: {key}")
    ctx.set_artifact(artifact_key, summary)
    return StepResult(ok=True, payload=summary)


def summarize(
    *,
    source: SourceLabel,
    niche: str,
    top_posts: list[dict[str, Any]],
    features: dict[str, Any],
) -> dict[str, Any]:
    """Return structured pattern summary; uses LLM when configured, else deterministic stub."""
    claude = get_claude_client()
    base = {
        "source": source,
        "post_count": len(top_posts),
        "features": features,
        "pattern_summary": "",
        "winning_topics": [],
        "voice_signals": [],
        "recommended_constraints": [],
    }
    if not top_posts:
        base["skipped"] = True
        base["skip_reason"] = "no_posts"
        return base

    if not claude.enabled:
        base["pattern_summary"] = (
            f"Top {len(top_posts)} {source.replace('_', ' ')} posts ranked by engagement; "
            "LLM pattern summary unavailable (no API key)."
        )
        return base

    system = _load_prompt("system")
    user = _load_prompt("user").format(
        source=source,
        niche=niche,
        post_count=len(top_posts),
        features_json=json.dumps(features, indent=2, default=str),
        posts_json=json.dumps(_trim_posts(top_posts), indent=2, default=str),
    )
    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
    except Exception as exc:
        base["errors"] = [str(exc)]
        return base

    if isinstance(data, dict):
        for key in ("pattern_summary", "winning_topics", "voice_signals", "recommended_constraints"):
            if key in data:
                base[key] = data[key]
    return base


def _load_prompt(suffix: str) -> str:
    path = f"tasks/{PROMPT_STEM}.{suffix}.md"
    try:
        return prompt_loader.load(path)
    except FileNotFoundError:
        if suffix == "system":
            return (
                "Analyze top-performing X posts for an account niche. "
                'Return JSON: {"pattern_summary": str, "winning_topics": [str], '
                '"voice_signals": [str], "recommended_constraints": [str]}.'
            )
        return (
            "Source: {source}\nNiche: {niche}\nPost count: {post_count}\n"
            "Features: {features_json}\nPosts: {posts_json}"
        )


def _trim_posts(posts: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in posts[:limit]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "tweet_id": row.get("tweet_id") or row.get("id"),
                "text": str(row.get("text") or "")[:500],
                "like_count": row.get("like_count"),
                "reply_count": row.get("reply_count"),
                "retweet_count": row.get("retweet_count"),
                "impression_count": row.get("impression_count"),
                "popularity_score": row.get("popularity_score"),
            }
        )
    return out

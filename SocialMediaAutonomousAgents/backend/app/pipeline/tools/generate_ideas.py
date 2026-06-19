"""LLM brainstorm of post concepts grounded in account soul and niche context."""

from __future__ import annotations

import json
from typing import Any

from app.infrastructure.claude_client import get_claude_client
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.generate_ideas"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Brainstorm post concepts from account soul and niche context"
TOOL_READS = (ArtifactKey.ACCOUNT_BUNDLE, ArtifactKey.TIMELINE_ANALYSIS)
TOOL_WRITES = (ArtifactKey.POST_IDEAS,)

_SYSTEM_PROMPT = (
    "You are a creative strategist for a social media account. "
    "Brainstorm 3-5 distinct post concept ideas that fit the account's voice and niche. "
    "Return a JSON array of objects, each with exactly two string fields: "
    '\"idea\" (one-sentence concept) and \"angle\" (the hook or framing). '
    "Example: [{\"idea\": \"...\", \"angle\": \"...\"}]. Return only the JSON array, no prose."
)

_USER_TEMPLATE = (
    "Account category: {category}\n"
    "Personality: {personality}\n"
    "Posting prompt: {posting_prompt}\n"
    "Niches: {niches}\n"
    "{trending_block}"
    "\nBrainstorm 3-5 post ideas."
)


def run(ctx: TickRunContext, config: dict) -> StepResult:
    account_bundle: dict[str, Any] = ctx.data.get("account_bundle") or {}
    timeline_analysis: dict[str, Any] | None = ctx.data.get("timeline_analysis")
    ideas = generate_ideas(account_bundle=account_bundle, timeline_analysis=timeline_analysis)
    ctx.set_artifact(ArtifactKey.POST_IDEAS, ideas)
    return StepResult(ok=True, payload=ideas)


def generate_ideas(
    *,
    account_bundle: dict[str, Any],
    timeline_analysis: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Return a list of idea dicts; uses LLM when configured, else returns a stub."""
    soul: dict[str, Any] = account_bundle.get("soul") or {}
    category: str = soul.get("category") or account_bundle.get("category") or ""
    personality: str = soul.get("personality") or ""
    posting_prompt: str = soul.get("posting_prompt") or ""
    niches: list[str] = soul.get("niches") or []

    trending_block = ""
    if timeline_analysis and isinstance(timeline_analysis, dict):
        summary = timeline_analysis.get("pattern_summary") or ""
        topics = timeline_analysis.get("winning_topics") or []
        if summary or topics:
            parts: list[str] = []
            if summary:
                parts.append(f"Trending context: {summary}")
            if topics:
                parts.append("Trending topics: " + ", ".join(str(t) for t in topics))
            trending_block = "\n".join(parts) + "\n"

    claude = get_claude_client()
    if not claude.enabled:
        return [
            {"idea": f"Share insight about {category or 'your niche'}", "angle": "Educational thread"},
            {"idea": "Behind-the-scenes look at your process", "angle": "Authenticity post"},
            {"idea": "Ask your audience a question", "angle": "Engagement prompt"},
        ]

    user = _USER_TEMPLATE.format(
        category=category,
        personality=personality,
        posting_prompt=posting_prompt,
        niches=", ".join(str(n) for n in niches) if niches else "general",
        trending_block=trending_block,
    )

    try:
        raw = claude.messages_json_dict(system=_SYSTEM_PROMPT, user=user, max_tokens=512)
    except Exception:
        return []

    return _parse_ideas(raw)


def _parse_ideas(raw: Any) -> list[dict[str, str]]:
    """Extract a list of {idea, angle} dicts from the LLM response."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        # Some models wrap the array: {"ideas": [...]} or {"result": [...]}
        for key in ("ideas", "result", "data"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        else:
            return []
    else:
        # Try parsing as a JSON string
        try:
            parsed = json.loads(str(raw))
            return _parse_ideas(parsed)
        except (json.JSONDecodeError, TypeError):
            return []

    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idea = str(item.get("idea") or "").strip()
        angle = str(item.get("angle") or "").strip()
        if idea:
            out.append({"idea": idea, "angle": angle})
    return out

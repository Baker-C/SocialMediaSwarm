"""LLM tool: translate a post idea into a concrete image or video generation prompt."""

from __future__ import annotations

from app.infrastructure.claude_client import get_claude_client
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.generate_media_prompt"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Translate a post idea into a concrete image or video generation prompt"
TOOL_READS = (ArtifactKey.POST_IDEAS,)
TOOL_WRITES = (ArtifactKey.MEDIA_PROMPT, ArtifactKey.MEDIA_PROMPT_A, ArtifactKey.MEDIA_PROMPT_B)


def run(
    ctx: TickRunContext,
    *,
    media_type: str = "image",
    variant: str | None = None,
) -> StepResult:
    ideas = ctx.data.get("post_ideas") or []
    if not ideas:
        return StepResult(ok=True, skipped=True, skip_reason="no_post_ideas")

    idea_entry = ideas[0] if isinstance(ideas, list) else ideas
    idea_text = idea_entry.get("idea", "") if isinstance(idea_entry, dict) else str(idea_entry)

    prompt_text = _generate_prompt(idea_text, media_type=media_type, variant=variant)

    if variant == "A":
        artifact_key = ArtifactKey.MEDIA_PROMPT_A
    elif variant == "B":
        artifact_key = ArtifactKey.MEDIA_PROMPT_B
    else:
        artifact_key = ArtifactKey.MEDIA_PROMPT

    result = {"prompt": prompt_text, "media_type": media_type, "variant": variant}
    ctx.set_artifact(artifact_key, result)
    return StepResult(ok=True, payload=result)


def _generate_prompt(idea: str, *, media_type: str, variant: str | None) -> str:
    """Call Claude to produce a generation prompt; returns a plain-text fallback when unavailable."""
    claude = get_claude_client()

    if not claude.enabled:
        return (
            f"A vivid, detailed {media_type} depicting: {idea}. "
            "High quality, professionally composed, suitable for AI generation."
        )

    system = (
        f"You are an expert prompt engineer for AI {media_type} generation. "
        "Write a single, vivid, specific generation prompt — no preamble, no explanation, "
        "just the prompt text itself."
    )

    if variant == "B":
        user = (
            f"Write a {media_type} generation prompt for this concept: {idea}. "
            "The prompt should be vivid, specific, and suitable for AI image/video generation. "
            "Use a CONTRASTING visual style from a typical interpretation: choose a different "
            "color palette, composition, and mood — but keep the same underlying concept."
        )
    else:
        user = (
            f"Write a {media_type} generation prompt for this concept: {idea}. "
            "The prompt should be vivid, specific, and suitable for AI image/video generation."
        )

    try:
        return claude.messages(system=system, user=user, max_tokens=512)
    except Exception as exc:
        return (
            f"A vivid, detailed {media_type} depicting: {idea}. "
            f"High quality, professionally composed. (generation error: {exc})"
        )

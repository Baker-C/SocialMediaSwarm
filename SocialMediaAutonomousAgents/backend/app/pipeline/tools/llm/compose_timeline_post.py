"""LLM compose step for timeline-reference posts."""

from __future__ import annotations

from app.interval.compose_timeline_post import compose_formatted_post
from app.interval.tweet_topic_preanalysis import GatheredTweet
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.compose_timeline_post"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Generate opinion + quip post body from a ranked reference tweet"
PROMPT_STEM = "compose_timeline_post"


def run(
    ctx: TickRunContext,
    *,
    winner: GatheredTweet,
    niche: str,
    account_system_prompt: str = "",
    account_personality: str = "",
    negative_semantics: list[str] | None = None,
    reference_context_block: str = "",
    regeneration_round: int = 0,
    safety_reject_reason: str | None = None,
) -> StepResult:
    body = compose_formatted_post(
        winner,
        niche,
        account_system_prompt=account_system_prompt,
        account_personality=account_personality,
        negative_semantics=negative_semantics,
        reference_context_block=reference_context_block,
        regeneration_round=regeneration_round,
        safety_reject_reason=safety_reject_reason,
    )
    ctx.set("composed_body", body)
    return StepResult(ok=True, payload={"body": body})

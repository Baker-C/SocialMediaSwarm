"""Kick off content generation + ranking for one account tick."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.hourly.pipeline_trace import trace_step
from app.hourly.schemas import TickBrief, TickInput, TickOutput
from app.hourly_crew import llm_pipeline

if TYPE_CHECKING:
    from app.agents.content_creator import ContentCreator


def run_content_pipeline(
    tick_input: TickInput,
    *,
    prompt_bundle: str,
    creator: ContentCreator | None = None,
    account_id: str | None = None,
    regeneration_round: int = 0,
) -> TickOutput:
    """
    Sequential LLM pipeline: generate candidates, then rank.

    When ``creator`` is provided (tests), delegates to its methods; otherwise uses
    ``llm_pipeline`` and prompt files.
    """
    aid = account_id or tick_input.account_id
    niche = tick_input.niche
    n = tick_input.max_candidates
    account_prompt = tick_input.account_system_prompt
    round_label = f"r{regeneration_round}"

    if creator is not None:
        candidates = creator.generate_candidates(niche, prompt_bundle, n)
    else:
        candidates = llm_pipeline.generate_candidates(
            niche,
            prompt_bundle,
            n,
            account_system_prompt=account_prompt,
        )
    trace_step(
        aid,
        f"crew_generate_candidates_{round_label}",
        {"count": len(candidates), "candidates": candidates},
        handoff_to="rank_candidates",
    )

    if creator is not None:
        ranked = creator.rank_candidates(candidates, prompt_bundle)
    else:
        ranked = llm_pipeline.rank_candidates(candidates, prompt_bundle)
    trace_step(
        aid,
        f"crew_rank_candidates_{round_label}",
        {"count": len(ranked), "ranked": ranked},
        handoff_to="TickOutput",
    )

    out = TickOutput(
        candidates=ranked,
        prompt_bundle=prompt_bundle,
        brief=TickBrief(prompt_bundle=prompt_bundle),
    )
    return out

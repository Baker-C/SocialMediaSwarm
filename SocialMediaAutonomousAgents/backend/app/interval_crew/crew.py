"""CrewAI crew assembly (sequential content pipeline)."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.interval.schemas import TickInput, TickOutput
from app.interval_crew import prompt_loader
from app.interval_crew.runner import run_content_pipeline

logger = logging.getLogger(__name__)


def _crew_llm():
    """Anthropic LLM for CrewAI when API key is configured."""
    from crewai import LLM

    return LLM(
        model=f"anthropic/{settings.claude_model}",
        api_key=settings.anthropic_api_key,
        temperature=0.7,
    )


def build_content_crew():
    """
    Build a sequential Crew for generate → rank.

    Falls back to direct ``run_content_pipeline`` when CrewAI is unavailable or
    Anthropic is not configured.
    """
    from crewai import Agent, Crew, Process, Task

    role = prompt_loader.parse_role_markdown("agents/content_creator.role.md")
    rank_role = prompt_loader.parse_role_markdown("agents/content_ranker.role.md")
    llm = _crew_llm()

    creator_agent = Agent(
        role=role["role"] or "Content Creator",
        goal=role["goal"] or "Write X posts",
        backstory=role["backstory"] or "",
        llm=llm,
        verbose=False,
    )
    ranker_agent = Agent(
        role=rank_role["role"] or "Content Ranker",
        goal=rank_role["goal"] or "Rank posts",
        backstory=rank_role["backstory"] or "",
        llm=llm,
        verbose=False,
    )

    generate_task = Task(
        description=(
            "Generate candidate X posts as JSON with key posts (array of strings). "
            "Each post should be one flowing, almost run-on thought (hook + context in the same breath), "
            "not multiple short clipped sentences. Use niche and context from inputs."
        ),
        expected_output='JSON object {"posts": ["..."]}',
        agent=creator_agent,
    )
    rank_task = Task(
        description="Rank the generated posts best-first; return JSON with key order (index list).",
        expected_output='JSON object {"order": [0, 1, ...]}',
        agent=ranker_agent,
        context=[generate_task],
    )

    return Crew(
        agents=[creator_agent, ranker_agent],
        tasks=[generate_task, rank_task],
        process=Process.sequential,
        verbose=False,
    )


def kickoff_content_pipeline(
    tick_input: TickInput,
    *,
    prompt_bundle: str,
    use_crew: bool = False,
) -> TickOutput:
    """
    Run the content pipeline.

    Default path uses ``llm_pipeline`` + prompt files (reliable JSON parsing).
    Set ``use_crew=True`` to run the CrewAI sequential crew when configured.
    """
    if use_crew and settings.anthropic_api_key:
        try:
            crew = build_content_crew()
            raw = crew.kickoff(
                inputs={
                    "niche": tick_input.niche,
                    "context": prompt_bundle[:10000],
                    "n": tick_input.max_candidates,
                },
            )
            logger.debug("crew kickoff raw: %s", str(raw)[:500])
        except Exception as exc:
            logger.warning("Crew kickoff failed, falling back to llm_pipeline: %s", exc)
    return run_content_pipeline(tick_input, prompt_bundle=prompt_bundle)

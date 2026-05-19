"""Rank-candidates step (implemented via llm_pipeline / crew.py)."""

from app.hourly_crew import llm_pipeline

__all__ = ["rank_candidates"]


def rank_candidates(candidates: list[str], prompt_bundle: str) -> list[str]:
    return llm_pipeline.rank_candidates(candidates, prompt_bundle)

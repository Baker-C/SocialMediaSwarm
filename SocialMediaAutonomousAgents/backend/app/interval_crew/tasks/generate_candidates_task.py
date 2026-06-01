"""Generate-candidates step (implemented via llm_pipeline / crew.py)."""

from app.interval_crew import llm_pipeline

__all__ = ["generate_candidates"]


def generate_candidates(
    niche: str,
    prompt_bundle: str,
    n: int,
    *,
    account_system_prompt: str = "",
) -> list[str]:
    return llm_pipeline.generate_candidates(
        niche,
        prompt_bundle,
        n,
        account_system_prompt=account_system_prompt,
    )

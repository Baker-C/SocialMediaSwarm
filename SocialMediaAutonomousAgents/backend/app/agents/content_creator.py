import logging

from app.agents.base_agent import BaseAgent
from app.hourly_crew import llm_pipeline

logger = logging.getLogger(__name__)


class ContentCreator(BaseAgent):
    def run(self):
        return self.generate_post("general", "topics")

    def generate_post(self, niche: str, trending_summary: str) -> str:
        posts = self.generate_candidates(niche, trending_summary, 1)
        return posts[0] if posts else ""

    def generate_candidates(self, niche: str, prompt_bundle: str, n: int) -> list[str]:
        """Up to ``n`` candidate posts; uses Claude + prompt files when configured."""
        return llm_pipeline.generate_candidates(niche, prompt_bundle, n)

    def rank_candidates(self, candidates: list[str], prompt_bundle: str) -> list[str]:
        """Return candidates sorted best-first using Claude + prompt files when configured."""
        return llm_pipeline.rank_candidates(candidates, prompt_bundle)

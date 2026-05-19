"""Content ranker agent wiring (see crew.py and prompt_loader)."""

from app.hourly_crew import prompt_loader


def load_content_ranker_role() -> dict[str, str]:
    return prompt_loader.parse_role_markdown("agents/content_ranker.role.md")

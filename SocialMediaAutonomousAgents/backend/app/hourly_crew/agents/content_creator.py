"""Content creator agent wiring (see crew.py and prompt_loader)."""

from app.hourly_crew import prompt_loader


def load_content_creator_role() -> dict[str, str]:
    return prompt_loader.parse_role_markdown("agents/content_creator.role.md")

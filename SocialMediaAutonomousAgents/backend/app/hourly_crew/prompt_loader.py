"""Load prompt templates from hourly_crew/prompts/."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"


def load(relative_path: str) -> str:
    path = _PROMPTS_ROOT / relative_path
    return path.read_text(encoding="utf-8").strip()


def load_template(relative_path: str, **variables: object) -> str:
    text = load(relative_path)
    if not variables:
        return text
    return text.format(**variables)


def parse_role_markdown(relative_path: str) -> dict[str, str]:
    """Parse content_creator.role.md sections into role, goal, backstory."""
    raw = load(relative_path)
    sections: dict[str, str] = {"role": "", "goal": "", "backstory": ""}
    current: str | None = None
    lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("# Role"):
            if current:
                sections[current] = "\n".join(lines).strip()
            current, lines = "role", []
        elif line.startswith("# Goal"):
            if current:
                sections[current] = "\n".join(lines).strip()
            current, lines = "goal", []
        elif line.startswith("# Backstory"):
            if current:
                sections[current] = "\n".join(lines).strip()
            current, lines = "backstory", []
        elif current is not None:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()
    return sections

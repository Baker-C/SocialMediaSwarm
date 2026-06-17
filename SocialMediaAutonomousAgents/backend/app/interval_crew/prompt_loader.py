"""Load prompt templates from interval_crew/prompts/."""

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

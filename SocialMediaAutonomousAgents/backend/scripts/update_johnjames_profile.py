#!/usr/bin/env python3
"""One-off: update JohnJames_News niche, personality, posting_prompt, and contrast_patterns."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.account import ContrastPattern, default_contrast_patterns  # noqa: E402
from app.services.account_repository import AccountRepository  # noqa: E402

ACCOUNT_ID = "JohnJames_News"
NICHE = "Broad News and Political Commentary"

PERSONALITY = """Snappy, provocative, left-leaning — not a Democratic Party loyalist or centrist cheerleader. Anti-establishment, anti-capitalist, anti-billionaire, anti-propaganda, anti-Trump. Skeptical of power, institutions, and corporate spin; call out who benefits and who gets hurt.

Write like someone in the country reacting live: energetic, emotional, upset or fired up when the story warrants it. Conversational X voice — loose grammar on purpose (spotty caps like spacex/musk/pentagon, emphatic caps like NOT, messy ?! punctuation, not every sentence perfectly punctuated). Never stiff, academic, or AI-polished."""

SYSTEM_PROMPT = """Each post has three parts. The app appends linked media from the source tweet automatically — do not put URLs in your JSON. No headline line.

1. Opinion — one to two sentences. Emotional, opinionated reaction to the story and linked media — like a real person venting, not a reporter. Use loose X grammar (inconsistent proper-noun caps, emphatic caps on key words, ?! allowed). Match personality.

2. Quip — one short follow line tailored to THIS story's topic. Same live voice. Vary wording.

3. Media URL — appended by the system; not part of your JSON output.

Stay on niche: Broad News and Political Commentary."""


def main() -> None:
    repo = AccountRepository()
    acc = repo.load(ACCOUNT_ID)
    if acc is None:
        raise SystemExit(f"Account not found: {ACCOUNT_ID}")
    acc.category = NICHE
    acc.personality = PERSONALITY
    acc.posting_prompt = SYSTEM_PROMPT
    acc.contrast_patterns = [ContrastPattern.model_validate(d) for d in default_contrast_patterns()]
    repo.save(acc)
    print(
        {
            "account_id": acc.account_id,
            "category": acc.category,
            "personality_len": len(acc.personality or ""),
            "posting_prompt_len": len(acc.posting_prompt or ""),
            "contrast_patterns_count": len(acc.contrast_patterns or []),
        }
    )


if __name__ == "__main__":
    main()

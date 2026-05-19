"""Assemble HEADLINE + story + source URL posts from timeline references."""

from __future__ import annotations

import logging
import re

from app.hourly.tweet_topic_preanalysis import GatheredTweet
from app.hourly_crew import prompt_loader
from app.infrastructure.claude_client import get_claude_client
from app.social.tweet_enrichment import select_chosen_post_media_url

logger = logging.getLogger(__name__)

_MAX_LEN = 280


def _fallback_compose(winner: GatheredTweet, niche: str) -> tuple[str, str]:
    words = re.sub(r"https?://\S+", "", winner.text)
    words = re.sub(r"#\w+", "", words).strip()
    parts = words.split()
    headline = " ".join(parts[:8])[:60] or f"{niche.strip()} update"
    story = " ".join(parts[:40])[:200] or headline
    return headline, story


def _parse_compose_json(data: dict) -> tuple[str, str] | None:
    if not isinstance(data, dict):
        return None
    headline = str(data.get("headline") or "").strip()
    story = str(data.get("story") or "").strip()
    if not headline or not story:
        return None
    return headline[:80], story[:220]


def compose_formatted_post(
    winner: GatheredTweet,
    niche: str,
    *,
    regeneration_round: int = 0,
) -> str:
    """
    Build post body: ``{headline}\\n\\n{story}\\n\\n{source_url}``.

    Truncates headline/story when needed; source URL is preserved at the end when present.
    """
    source_row = {**winner.metrics, "id": winner.tweet_id, "tweet_id": winner.tweet_id}
    source_url = select_chosen_post_media_url(source_row) or ""
    claude = get_claude_client()
    headline, story = _fallback_compose(winner, niche)

    if claude.enabled:
        try:
            system = prompt_loader.load("tasks/compose_timeline_post.system.md")
            regen_hint = ""
            if regeneration_round > 0:
                regen_hint = (
                    f"\n\nThis is regeneration attempt {regeneration_round + 1}; "
                    "vary wording while keeping the same facts."
                )
            user = prompt_loader.load_template(
                "tasks/compose_timeline_post.user.md",
                niche=(niche or "general").strip(),
                tweet_id=winner.tweet_id,
                interaction_score=winner.interaction_score,
                source_text=winner.text[:2000],
            )
            user += regen_hint
            data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
            parsed = _parse_compose_json(data) if isinstance(data, dict) else None
            if parsed:
                headline, story = parsed
        except Exception as exc:
            logger.warning("compose_timeline_post LLM failed: %s", exc)

    return assemble_formatted_body(headline, story, source_url)


def assemble_formatted_body(
    headline: str,
    story: str,
    permalink: str,
    *,
    max_len: int = _MAX_LEN,
) -> str:
    """Assemble and fit within X character limit; URL stays at the end when possible."""
    link = (permalink or "").strip()
    headline = (headline or "").strip()
    story = (story or "").strip()

    def build(h: str, s: str) -> str:
        if h and s:
            body = f"{h}\n\n{s}"
        elif h:
            body = h
        else:
            body = s
        if link:
            return f"{body}\n\n{link}" if body else link
        return body

    candidate = build(headline, story)
    if len(candidate) <= max_len:
        return candidate

    for h_len in range(len(headline), 20, -5):
        for s_len in range(len(story), 40, -10):
            candidate = build(headline[:h_len].rstrip(), story[:s_len].rstrip())
            if len(candidate) <= max_len:
                return candidate

    if link:
        overhead = len(f"\n\n{link}")
        room = max_len - overhead
        minimal = headline[: max(0, room)].rstrip()
        return f"{minimal}\n\n{link}" if minimal else link[:max_len]
    return candidate[:max_len]

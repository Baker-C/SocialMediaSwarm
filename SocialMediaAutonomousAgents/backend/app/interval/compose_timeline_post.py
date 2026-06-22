"""Assemble a soul-driven post + source URL from a timeline reference.

The account's soul (personality + posting instructions + contrast patterns) decides
the post's voice, structure, and length-feel. This module only conveys that soul to
the model and enforces the character limit (including the appended URL). If a post
cannot be generated within budget it returns ``None`` — the caller skips the post and
logs the reason rather than publishing fabricated or truncated content.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.interval.tweet_topic_preanalysis import GatheredTweet
from app.models.account import format_contrast_patterns_for_prompt
from app.interval.orchestration.voice_polish import polish_text
from app.interval_crew import prompt_loader
from app.infrastructure.claude_client import get_claude_client
from app.agents.safety_guardian import is_niche_mismatch_reject
from app.social.tweet_enrichment import select_chosen_post_media_url

logger = logging.getLogger(__name__)

MAX_POST_LEN = 280
COMPOSE_LENGTH_MAX_ATTEMPTS = 4


@dataclass(frozen=True)
class PostLengthBudget:
    max_post_len: int
    link: str
    link_char_count: int
    body_char_budget: int


def compute_post_length_budget(link: str, *, max_post_len: int = MAX_POST_LEN) -> PostLengthBudget:
    """Reserve characters for the appended link, leaving the rest for the post text."""
    url = (link or "").strip()
    link_suffix = f"\n\n{url}" if url else ""
    link_chars = len(link_suffix)
    body_budget = max(0, max_post_len - link_chars)
    return PostLengthBudget(
        max_post_len=max_post_len,
        link=url,
        link_char_count=link_chars,
        body_char_budget=body_budget,
    )


def assemble_formatted_body(text: str, permalink: str) -> str:
    """Join the post text and optional link (no truncation)."""
    body = (text or "").strip()
    link = (permalink or "").strip()
    if link:
        return f"{body}\n\n{link}" if body else link
    return body


def assembled_post_length(text: str, link: str) -> int:
    return len(assemble_formatted_body(text, link))


def fits_post_budget(text: str, budget: PostLengthBudget) -> bool:
    return assembled_post_length(text, budget.link) <= budget.max_post_len


def _parse_compose_json(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    post = str(data.get("post") or data.get("text") or data.get("body") or "").strip()
    return post or None


def _length_retry_hint(budget: PostLengthBudget, previous: str, attempt: int) -> str:
    over_by = assembled_post_length(previous, budget.link) - budget.max_post_len
    return (
        f"\n\nREGENERATION {attempt + 1} — previous post was too long by {over_by} characters. "
        f"Your post must be at most {budget.body_char_budget} characters; do not include the link."
    )


def _personality_section(account_personality: str) -> str:
    p = (account_personality or "").strip()
    if not p:
        return "(No personality profile — conversational, direct, human-sounding.)"
    return p


def _generate_post_body(
    winner: GatheredTweet,
    niche: str,
    budget: PostLengthBudget,
    *,
    account_posting_prompt: str = "",
    account_personality: str = "",
    contrast_patterns: list | None = None,
    reference_context_block: str = "",
    regeneration_round: int,
    length_attempt: int,
    previous: str | None,
    safety_reject_reason: str | None = None,
) -> str | None:
    """Ask the model for a single soul-driven post. Returns ``None`` when the LLM is
    disabled or the call/parse fails — no fabricated fallback."""
    claude = get_claude_client()
    if not claude.enabled:
        return None

    system = prompt_loader.load("tasks/compose_timeline_post.system.md")
    append_display = budget.link if budget.link else "(none — no link on this post)"
    posting_instructions = (account_posting_prompt or "").strip() or (
        "(No posting instructions — follow the personality and keep it natural and human.)"
    )
    ref_block = (reference_context_block or "").strip() or "(No reference analysis available for this tick.)"
    user = prompt_loader.load_template(
        "tasks/compose_timeline_post.user.md",
        niche=(niche or "general").strip(),
        account_system_prompt=posting_instructions,    # template var name kept for the soul's posting prompt
        account_personality=_personality_section(account_personality),
        # contrast patterns rendered as avoid/lean blocks
        negative_semantics_block=format_contrast_patterns_for_prompt(contrast_patterns),
        reference_context_block=ref_block,
        tweet_id=winner.tweet_id,
        popularity_score=winner.popularity_score,
        source_text=winner.text[:2000],
        body_char_budget=budget.body_char_budget,
        append_url=append_display,
    )
    if regeneration_round > 0:
        user += (
            f"\n\nSafety regeneration pass {regeneration_round + 1}; "
            "vary wording while keeping the same facts."
        )
    if safety_reject_reason and is_niche_mismatch_reject(safety_reject_reason):
        detail = safety_reject_reason.split(":", 1)[-1].strip()
        user += (
            f"\n\nPrevious draft was rejected — it did not fit the account niche ({niche.strip()}). "
            f"Reason: {detail}. "
            "Rewrite about the same source facts but make the topic clearly on-niche."
        )
    if length_attempt > 0 and previous is not None:
        user += _length_retry_hint(budget, previous, length_attempt)

    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
        return _parse_compose_json(data) if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("compose_timeline_post LLM failed: %s", exc)
        return None


def compose_formatted_post(
    winner: GatheredTweet,
    niche: str,
    *,
    account_posting_prompt: str = "",
    account_personality: str = "",
    contrast_patterns: list | None = None,
    punctuation_rules: list | None = None,
    reference_context_block: str = "",
    regeneration_round: int = 0,
    safety_reject_reason: str | None = None,
) -> str | None:
    """Build ``{post}\\n\\n{source_url}`` within 280 characters.

    The link length is reserved first; the model is given the remaining budget and
    retried until the assembled post fits. Returns ``None`` (caller skips + logs) when
    the LLM is unavailable, generation fails, or no draft fits — never a fabricated or
    truncated post.
    """
    source_row = {**winner.metrics, "id": winner.tweet_id, "tweet_id": winner.tweet_id}
    source_url = select_chosen_post_media_url(source_row) or ""
    budget = compute_post_length_budget(source_url)

    previous: str | None = None
    for length_attempt in range(COMPOSE_LENGTH_MAX_ATTEMPTS):
        text = _generate_post_body(
            winner,
            niche,
            budget,
            account_posting_prompt=account_posting_prompt,
            account_personality=account_personality,
            contrast_patterns=contrast_patterns,
            reference_context_block=reference_context_block,
            regeneration_round=regeneration_round,
            length_attempt=length_attempt,
            previous=previous,
            safety_reject_reason=safety_reject_reason,
        )
        if text is None:
            logger.warning(
                "compose_timeline_post: no post generated tweet_id=%s "
                "(LLM disabled or generation failed) — skipping",
                winner.tweet_id,
            )
            return None
        # Punctuation auto-fix BEFORE the budget check, so length-changing fixes
        # (em-dash → ", ", removals) can't push the assembled post over 280.
        text = polish_text(text, punctuation_rules).polished
        if fits_post_budget(text, budget):
            body = assemble_formatted_body(text, source_url)
            logger.info(
                "compose_timeline_post ok tweet_id=%s len=%s budget=%s attempt=%s",
                winner.tweet_id,
                len(body),
                budget.body_char_budget,
                length_attempt,
            )
            return body
        previous = text
        logger.warning(
            "compose_timeline_post too long tweet_id=%s len=%s max=%s attempt=%s/%s",
            winner.tweet_id,
            assembled_post_length(text, source_url),
            budget.max_post_len,
            length_attempt + 1,
            COMPOSE_LENGTH_MAX_ATTEMPTS,
        )

    logger.warning(
        "compose_timeline_post: could not fit budget after %s attempts tweet_id=%s — skipping",
        COMPOSE_LENGTH_MAX_ATTEMPTS,
        winner.tweet_id,
    )
    return None

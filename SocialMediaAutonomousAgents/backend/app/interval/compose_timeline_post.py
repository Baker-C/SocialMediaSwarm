"""Assemble opinion + quip + source URL posts from timeline references."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.interval.tweet_topic_preanalysis import GatheredTweet
from app.models.account import format_negative_semantics_for_prompt
from app.interval_crew import prompt_loader
from app.infrastructure.claude_client import get_claude_client
from app.agents.safety_guardian import is_niche_mismatch_reject
from app.social.tweet_enrichment import select_chosen_post_media_url

logger = logging.getLogger(__name__)

MAX_POST_LEN = 280
BODY_SEPARATOR_LEN = 2  # "\n\n" between opinion and quip
TEXT_BLOCK_SEPARATORS = 1
COMPOSE_LENGTH_MAX_ATTEMPTS = 4
_OPINION_SHARE = 0.72
_OPINION_CAP = 200
_OPINION_FLOOR = 40
_QUIP_SHARE = 0.28
_QUIP_CAP = 65
_QUIP_FLOOR = 15


@dataclass(frozen=True)
class PostLengthBudget:
    max_post_len: int
    link: str
    link_char_count: int
    body_char_budget: int
    text_separator_char_count: int
    opinion_char_max: int
    quip_char_max: int

    @property
    def commentary_char_max(self) -> int:
        return self.opinion_char_max

    @property
    def story_char_max(self) -> int:
        return self.opinion_char_max

    @property
    def headline_char_max(self) -> int:
        return 0


def compute_post_length_budget(link: str, *, max_post_len: int = MAX_POST_LEN) -> PostLengthBudget:
    """Reserve characters for the appended link before the LLM writes text blocks."""
    url = (link or "").strip()
    link_suffix = f"\n\n{url}" if url else ""
    link_chars = len(link_suffix)
    body_budget = max(0, max_post_len - link_chars)
    sep_chars = TEXT_BLOCK_SEPARATORS * BODY_SEPARATOR_LEN
    content_budget = max(0, body_budget - sep_chars)

    quip_max = min(
        _QUIP_CAP,
        max(_QUIP_FLOOR, int(content_budget * _QUIP_SHARE)),
    )
    quip_max = min(quip_max, content_budget)
    opinion_max = min(
        _OPINION_CAP,
        max(_OPINION_FLOOR, content_budget - quip_max),
    )

    return PostLengthBudget(
        max_post_len=max_post_len,
        link=url,
        link_char_count=link_chars,
        body_char_budget=body_budget,
        text_separator_char_count=sep_chars,
        opinion_char_max=opinion_max,
        quip_char_max=quip_max,
    )


def assemble_formatted_body(opinion: str, quip: str, permalink: str) -> str:
    """Join opinion, quip, and optional link (no truncation)."""
    link = (permalink or "").strip()
    blocks = [b.strip() for b in (opinion, quip) if b and b.strip()]
    body = "\n\n".join(blocks)
    if link:
        return f"{body}\n\n{link}" if body else link
    return body


def assembled_post_length(opinion: str, quip: str, link: str) -> int:
    return len(assemble_formatted_body(opinion, quip, link))


def fits_post_budget(opinion: str, quip: str, budget: PostLengthBudget) -> bool:
    return assembled_post_length(opinion, quip, budget.link) <= budget.max_post_len


def _topic_tailored_quip(source_text: str, niche: str, *, max_len: int) -> str:
    """Fallback CTA when the LLM is off — rough topic match from source text."""
    t = (source_text or "").lower()
    if any(w in t for w in ("bitcoin", "crypto", "ethereum", "btc", "defi", "blockchain")):
        line = "Follow for sharp crypto analysis and market takes"
    elif any(w in t for w in ("war", "ukraine", "gaza", "nato", "missile", "airstrike", "ceasefire")):
        line = "Follow for global conflict and world news commentary"
    elif any(
        w in t
        for w in (
            "election",
            "congress",
            "senate",
            "white house",
            "parliament",
            "minister",
            "president",
            "democrat",
            "republican",
            "vote",
            "ballot",
        )
    ):
        line = "Follow for political news and commentary that cuts through the spin"
    elif any(w in t for w in ("market", "fed", "inflation", "stocks", "economy", "jobs report", "gdp")):
        line = "Follow for economy and markets explained fast"
    elif any(w in t for w in ("court", "ruling", "lawsuit", "indictment", "justice", "scotus")):
        line = "Follow for legal and power-structure breakdowns"
    elif any(w in t for w in ("climate", "hurricane", "earthquake", "flood", "wildfire")):
        line = "Follow for crisis and global news as it breaks"
    else:
        label = (niche or "news").strip()
        line = f"Follow for {label.lower()} — fast takes that matter"
    return line[:max_len].strip()


def _fallback_compose(winner: GatheredTweet, niche: str, budget: PostLengthBudget) -> tuple[str, str]:
    words = re.sub(r"https?://\S+", "", winner.text)
    words = re.sub(r"#\w+", "", words).strip()
    parts = words.split()
    opinion = (" ".join(parts[:40]) or f"{niche.strip()} update")[: budget.opinion_char_max]
    quip = _topic_tailored_quip(words, niche, max_len=budget.quip_char_max)
    return opinion.strip(), quip.strip()


def _parse_compose_json(data: dict) -> tuple[str, str] | None:
    if not isinstance(data, dict):
        return None
    opinion = str(
        data.get("opinion") or data.get("commentary") or data.get("story") or data.get("headline") or ""
    ).strip()
    quip = str(data.get("quip") or "").strip()
    if not opinion or not quip:
        return None
    return opinion, quip


def _shrink_to_budget(opinion: str, quip: str, budget: PostLengthBudget) -> tuple[str, str]:
    """Last resort when the LLM cannot fit limits after all retries."""
    o = opinion.strip()[: budget.opinion_char_max]
    q = quip.strip()[: budget.quip_char_max]
    while not fits_post_budget(o, q, budget) and (len(o) > 8 or len(q) > 8):
        if len(o) > 8:
            o = o[: max(8, len(o) - 12)].rsplit(" ", 1)[0] or o[:8]
        elif len(q) > 8:
            q = q[: max(8, len(q) - 10)].rsplit(" ", 1)[0] or q[:8]
        else:
            break
    return o.strip(), q.strip()


def _length_retry_hint(
    budget: PostLengthBudget,
    opinion: str,
    quip: str,
    attempt: int,
) -> str:
    actual = assembled_post_length(opinion, quip, budget.link)
    over_by = actual - budget.max_post_len
    text_budget = budget.body_char_budget - budget.text_separator_char_count
    return (
        f"\n\nREGENERATION {attempt + 1} — previous JSON was too long by {over_by} characters. "
        f"Opinion + quip must be at most {text_budget} characters combined "
        f"(opinion ≤ {budget.opinion_char_max}, quip ≤ {budget.quip_char_max}). "
        "Shorten both; do not include the link in your JSON."
    )


def _personality_section(account_personality: str) -> str:
    p = (account_personality or "").strip()
    if not p:
        return "(No personality profile — conversational, direct, human-sounding.)"
    return p


def _generate_post_parts(
    winner: GatheredTweet,
    niche: str,
    budget: PostLengthBudget,
    *,
    account_system_prompt: str = "",
    account_personality: str = "",
    negative_semantics: list[str] | None = None,
    regeneration_round: int,
    length_attempt: int,
    previous: tuple[str, str] | None,
    safety_reject_reason: str | None = None,
) -> tuple[str, str]:
    claude = get_claude_client()
    opinion, quip = _fallback_compose(winner, niche, budget)

    if not claude.enabled:
        return _shrink_to_budget(opinion, quip, budget)

    system = prompt_loader.load("tasks/compose_timeline_post.system.md")
    append_display = budget.link if budget.link else "(none — no link on this post)"
    structure = (account_system_prompt or "").strip() or (
        "Energetic, emotional opinion on the story and linked media, then a topic-tailored quip. "
        "Loose X grammar (spotty caps, emphatic NOT, ?!) — like someone in the country venting, not AI."
    )
    user = prompt_loader.load_template(
        "tasks/compose_timeline_post.user.md",
        niche=(niche or "general").strip(),
        account_system_prompt=structure,
        account_personality=_personality_section(account_personality),
        negative_semantics_block=format_negative_semantics_for_prompt(negative_semantics),
        tweet_id=winner.tweet_id,
        popularity_score=winner.popularity_score,
        source_text=winner.text[:2000],
        max_post_len=budget.max_post_len,
        link_char_count=budget.link_char_count,
        append_url=append_display,
        body_char_budget=budget.body_char_budget,
        text_block_budget=budget.body_char_budget - budget.text_separator_char_count,
        opinion_char_max=budget.opinion_char_max,
        quip_char_max=budget.quip_char_max,
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
    if length_attempt > 0 and previous:
        user += _length_retry_hint(budget, previous[0], previous[1], length_attempt)

    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
        parsed = _parse_compose_json(data) if isinstance(data, dict) else None
        if parsed:
            return parsed
    except Exception as exc:
        logger.warning("compose_timeline_post LLM failed: %s", exc)

    return opinion, quip


def compose_formatted_post(
    winner: GatheredTweet,
    niche: str,
    *,
    account_system_prompt: str = "",
    account_personality: str = "",
    negative_semantics: list[str] | None = None,
    regeneration_round: int = 0,
    safety_reject_reason: str | None = None,
) -> str:
    """
    Build ``{opinion}\\n\\n{quip}\\n\\n{source_url}`` within 280 characters.

    Link length is reserved first; the LLM is given the remaining budget and retried
    until the assembled post fits (no post-hoc truncation except a final fallback).
    """
    source_row = {**winner.metrics, "id": winner.tweet_id, "tweet_id": winner.tweet_id}
    source_url = select_chosen_post_media_url(source_row) or ""
    budget = compute_post_length_budget(source_url)

    opinion, quip = _fallback_compose(winner, niche, budget)
    previous: tuple[str, str] | None = None

    for length_attempt in range(COMPOSE_LENGTH_MAX_ATTEMPTS):
        opinion, quip = _generate_post_parts(
            winner,
            niche,
            budget,
            account_system_prompt=account_system_prompt,
            account_personality=account_personality,
            negative_semantics=negative_semantics,
            regeneration_round=regeneration_round,
            length_attempt=length_attempt,
            previous=previous,
            safety_reject_reason=safety_reject_reason,
        )
        if fits_post_budget(opinion, quip, budget):
            body = assemble_formatted_body(opinion, quip, source_url)
            logger.info(
                "compose_timeline_post ok tweet_id=%s len=%s budget=%s attempt=%s",
                winner.tweet_id,
                len(body),
                budget.body_char_budget,
                length_attempt,
            )
            return body
        previous = (opinion, quip)
        logger.warning(
            "compose_timeline_post too long tweet_id=%s len=%s max=%s attempt=%s/%s",
            winner.tweet_id,
            assembled_post_length(opinion, quip, source_url),
            budget.max_post_len,
            length_attempt + 1,
            COMPOSE_LENGTH_MAX_ATTEMPTS,
        )

    opinion, quip = _shrink_to_budget(opinion, quip, budget)
    body = assemble_formatted_body(opinion, quip, source_url)
    logger.warning(
        "compose_timeline_post fallback shrink tweet_id=%s len=%s",
        winner.tweet_id,
        len(body),
    )
    return body

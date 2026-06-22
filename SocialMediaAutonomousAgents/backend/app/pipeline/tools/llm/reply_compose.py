"""Coarse reply tool: DECIDE (reply|skip) then compose a guardian-safe reply to a mention (doc 12).

Writes REPLY_VERDICT always; REPLY_DRAFT only when replying.
"""

from __future__ import annotations

from app.agents.safety_guardian import is_niche_mismatch_reject
from app.interval.compose_timeline_post import compose_formatted_post
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "llm.reply_compose"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Decide whether to reply to a ranked mention, then compose a guardian-safe reply"
TOOL_READS = (ArtifactKey.MENTIONS_RANKED,)
TOOL_WRITES = (ArtifactKey.REPLY_DRAFT, ArtifactKey.REPLY_VERDICT)


def _mention_score(mention: dict) -> float:
    """Score a mention by engagement metrics (same logic as reference ranking)."""
    like_count = mention.get("like_count") or 0
    reply_count = mention.get("reply_count") or 0
    retweet_count = mention.get("retweet_count") or 0
    return float(like_count + 2 * reply_count + retweet_count)


def _mention_tweet_id(mention: dict) -> str:
    """Extract tweet id from a mention row."""
    return mention.get("tweet_id") or mention.get("id") or ""


def _mention_author_handle(mention: dict) -> str | None:
    """Extract author handle from a mention row."""
    return mention.get("author_handle") or mention.get("author") or None


def _format_mention_for_reply(mention: dict) -> str:
    """Format the mention text as reply context block."""
    text = mention.get("text") or ""
    handle = _mention_author_handle(mention)
    if handle:
        return f"Mention from @{handle}: {text}"
    return f"Mention: {text}"


def _mention_as_winner(mention: dict) -> dict:
    """Adapt the mention row to a GatheredTweet-like dict for compose_formatted_post."""
    return {
        "id": _mention_tweet_id(mention),
        "text": mention.get("text") or "",
        "author": _mention_author_handle(mention),
        "like_count": mention.get("like_count") or 0,
        "reply_count": mention.get("reply_count") or 0,
        "retweet_count": mention.get("retweet_count") or 0,
    }


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    cfg = ctx.data.get("_step_config:llm.reply_compose", {})
    min_score = float(cfg.get("min_mention_score", 0.0))
    live = deps.live
    max_rounds = max(1, int(live.max_regeneration_rounds))
    guardian = live.guardian
    account = live.account

    ranked = ctx.get_artifact(ArtifactKey.MENTIONS_RANKED)
    candidates = list(getattr(ranked, "ranked", None) or [])

    # ── DECIDE: pick the first mention worth answering, or skip ──────────────
    winner = next((m for m in candidates if _mention_score(m) >= min_score), None)
    if winner is None:
        ctx.set_artifact(
            ArtifactKey.REPLY_VERDICT,
            {"decision": "skip", "reason": "no_mention_above_threshold"},
        )
        return StepResult(
            ok=True, skipped=True, skip_reason="no_mention_above_threshold"
        )

    # ── ACT-compose: regenerate-with-guardian-feedback (same loop as compose_until_safe) ──
    target_tweet_id = _mention_tweet_id(winner)
    target_handle = _mention_author_handle(winner)
    reply_context = _format_mention_for_reply(winner)
    selected_body: str | None = None
    selected_round = 0
    last_reject: str | None = None
    candidate_reject: str | None = None
    for reg_round in range(max_rounds):
        body = compose_formatted_post(
            _mention_as_winner(winner),
            account.category,
            account_posting_prompt=(account.posting_prompt or "").strip(),
            account_personality=(account.personality or "").strip(),
            contrast_patterns=list(account.contrast_patterns or []),
            punctuation_rules=list(account.punctuation_rules or []),
            reference_context_block=reply_context,
            regeneration_round=reg_round,
            safety_reject_reason=candidate_reject if reg_round > 0 else None,
        )
        if body is None:
            # Compose could not produce a reply (LLM unavailable or generation failed) —
            # skip cleanly rather than replying with fabricated content.
            ctx.set_artifact(
                ArtifactKey.REPLY_VERDICT,
                {"decision": "skip", "reason": "compose_failed",
                 "in_reply_to_tweet_id": target_tweet_id},
            )
            return StepResult(ok=True, skipped=True, skip_reason="compose_failed")
        approved, reject = guardian.evaluate(body, niche=account.category)
        if approved:
            selected_body, selected_round = body, reg_round
            break
        candidate_reject = reject or "safety_rejected"
        if is_niche_mismatch_reject(candidate_reject):
            last_reject = candidate_reject
            break

    if selected_body is None:
        ctx.set_artifact(
            ArtifactKey.REPLY_VERDICT,
            {
                "decision": "skip",
                "reason": last_reject or "all_reply_attempts_failed",
            },
        )
        return StepResult(
            ok=True,
            skipped=True,
            skip_reason=last_reject or "all_reply_attempts_failed",
        )

    ctx.set_artifact(
        ArtifactKey.REPLY_DRAFT,
        {
            "body": selected_body,
            "in_reply_to_tweet_id": target_tweet_id,
            "target_author_handle": target_handle,
            "regeneration_round": selected_round,
        },
    )
    ctx.set_artifact(
        ArtifactKey.REPLY_VERDICT,
        {
            "decision": "reply",
            "approved": True,
            "in_reply_to_tweet_id": target_tweet_id,
        },
    )
    return StepResult(ok=True, payload={"in_reply_to_tweet_id": target_tweet_id})

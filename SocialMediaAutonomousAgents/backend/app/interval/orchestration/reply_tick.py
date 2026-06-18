"""Publish + persist a reply. Reply analogue of finalize_post, WITHOUT the interval-slot
/ posts_total / copied-reference / snapshot mutations (doc 12).
"""

from __future__ import annotations

import logging
from typing import Any

from app.interval.context import TickContext
from app.models.account import AccountDocument
from app.models.tracked_post import PostCreationMetrics
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)


def finalize_reply(
    ctx: TickContext,
    account: AccountDocument,
    body: str,
    *,
    in_reply_to_tweet_id: str,
    target_author_handle: str | None = None,
    creation_metrics: PostCreationMetrics | None = None,
) -> dict[str, Any]:
    """Publish a reply in-reply-to a mention and record it.

    Unlike finalize_post, this does NOT consume an interval slot, bump posts_total,
    or snapshot the account. A reply is a separate behavior, keyed to a mention.
    """
    outcomes = PipelineOutcomeRepository()
    try:
        tw_result = ctx.twitter.post_tweet(
            account.account_id, body, in_reply_to=in_reply_to_tweet_id
        )
    except Exception as exc:
        logger.warning("reply failed for %s: %s", account.account_id, exc)
        outcomes.append(
            account_id=account.account_id,
            phase="finalize_reply",
            status="error",
            reason="reply_failed",
            details={"error": str(exc)},
        )
        return {"account_id": account.account_id, "error": str(exc)}

    reply_id = str(tw_result.get("id") or "")
    if ctx.post_registry:
        try:
            ctx.post_registry.record_post(
                account.account_id,
                reply_id,
                ctx.now_iso,
                creation_metrics=creation_metrics,
            )
        except Exception as exc:
            logger.warning("reply registry record failed: %s", exc)
    outcomes.append(
        account_id=account.account_id, phase="finalize_reply", status="ok"
    )
    return {
        "account_id": account.account_id,
        "tweet": tw_result,
        "in_reply_to_tweet_id": in_reply_to_tweet_id,
    }

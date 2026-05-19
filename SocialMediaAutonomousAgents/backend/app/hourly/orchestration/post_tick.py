"""Deterministic post-crew: publish, registry, account persist."""

from __future__ import annotations

import logging
from typing import Any

from app.hourly.context import TickContext
from app.hourly.orchestration.post_guard import release_post_guard
from app.hourly.orchestration.slot_claim import (
    finalize_hourly_slot_reservation,
    release_hourly_slot_reservation,
)
from app.models.account import AccountDocument
from app.models.tracked_post import PostCreationMetrics

logger = logging.getLogger(__name__)


def finalize_post(
    ctx: TickContext,
    account: AccountDocument,
    selected_body: str,
    *,
    regeneration_round: int | None,
    earlier_reject: str | None,
    creation_metrics: PostCreationMetrics | None = None,
) -> dict[str, Any]:
    try:
        tw_result = ctx.twitter.post_tweet(account.account_id, selected_body)
    except Exception as exc:
        logger.warning("post failed for %s after selection: %s", account.account_id, exc)
        release_hourly_slot_reservation(ctx, account.account_id)
        release_post_guard(ctx, account.account_id)
        return {"account_id": account.account_id, "error": str(exc)}

    account.posts_total += 1
    if ctx.mode == "scheduled":
        account.last_post_slot = ctx.slot
    account.last_post_id = str(tw_result.get("id") or "")
    account.last_post_text = str(tw_result.get("text") or selected_body)
    account.last_post_at = ctx.now_iso
    if ctx.post_registry:
        try:
            ctx.post_registry.record_post(
                account.account_id,
                account.last_post_id,
                ctx.now_iso,
                creation_metrics=creation_metrics,
            )
            m = ctx.twitter.get_tweet_metrics(account.account_id, account.last_post_id)
            imp = m.get("impression_count")
            if isinstance(imp, int):
                account.last_post_views = imp
            if m.get("tweet_permalink") or m.get("media_types") or m.get("embed_urls"):
                ctx.post_registry.update_enrichment(account.account_id, account.last_post_id, m)
        except Exception as exc:
            logger.warning("post-registry / metrics priming failed: %s", exc)
    ctx.repo.save(account)
    finalize_hourly_slot_reservation(ctx, account.account_id)
    release_post_guard(ctx, account.account_id)
    out: dict[str, Any] = {
        "account_id": account.account_id,
        "tweet": tw_result,
        "regeneration_round": regeneration_round,
    }
    if earlier_reject:
        out["note"] = f"earlier_rejections_including:{earlier_reject}"
    if creation_metrics is not None:
        out["creation_metrics"] = creation_metrics.model_dump(exclude_none=True)
    return out


def phase3_global_persist(ctx: TickContext) -> None:
    logger.debug("phase3_global_persist: tick slot=%s mode=%s (no extra flush)", ctx.slot, ctx.mode)


def phase4_backup_noop() -> None:
    logger.debug("phase4_backup: RavenDB backups are an ops concern; application tick does not run backups.")

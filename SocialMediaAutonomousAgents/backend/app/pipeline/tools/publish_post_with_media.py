"""Upload media to X and publish the tweet (terminal step for media pipelines).

Reads COMPOSED_POST_WITH_MEDIA (text + media_keys) and resolves each media key
to a MediaRef artifact, hydrates its bytes from MediaAssetRepository, then calls
TwitterService.post_tweet_with_media.  Post-publish state management (account
document, post registry, outcome ledger, snapshot) mirrors finalize_post in
app.interval.orchestration.post_tick so the account stays consistent.

Idempotency: same (run_id, account_id) ledger as publish_post — a retry in the
same run returns the first tweet_id without re-posting.
"""

from __future__ import annotations

import logging
from typing import Any

from app.interval.orchestration.post_guard import release_post_guard
from app.interval.orchestration.slot_claim import (
    finalize_interval_slot_reservation,
    release_interval_slot_reservation,
)
from app.interval_crew.tools.take_snapshot_tool import take_snapshot
from app.models.tracked_post import PostCreationMetrics
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey, MediaRef
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.copied_references import record_copied_reference
from app.services.media_asset_repository import MediaAssetRepository
from app.services.outcome_ledger_repository import OutcomeLedgerRepository
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

logger = logging.getLogger(__name__)

TOOL_ID = "data.publish_post_with_media"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Upload media to X and publish the tweet (terminal step for media pipelines)"
TOOL_READS = (
    ArtifactKey.COMPOSED_POST_WITH_MEDIA,
    ArtifactKey.ACCOUNT_BUNDLE,
    ArtifactKey.GENERATED_IMAGE,
    ArtifactKey.GENERATED_IMAGE_A,
    ArtifactKey.GENERATED_IMAGE_B,
    ArtifactKey.GENERATED_VIDEO,
    ArtifactKey.GENERATED_VIDEO_A,
    ArtifactKey.GENERATED_VIDEO_B,
)
TOOL_WRITES = (ArtifactKey.PUBLISHED_POST,)

# Process-local idempotency ledger: (run_id, account_id) → tweet_id already posted.
_POSTED: dict[tuple[str, str], str] = {}

# Canonical map from artifact key string to ArtifactKey enum for media variants.
_MEDIA_ARTIFACT_KEYS: dict[str, ArtifactKey] = {
    "generated_image": ArtifactKey.GENERATED_IMAGE,
    "generated_image_a": ArtifactKey.GENERATED_IMAGE_A,
    "generated_image_b": ArtifactKey.GENERATED_IMAGE_B,
    "generated_video": ArtifactKey.GENERATED_VIDEO,
    "generated_video_a": ArtifactKey.GENERATED_VIDEO_A,
    "generated_video_b": ArtifactKey.GENERATED_VIDEO_B,
}


def _followers_at_post(ctx: TickRunContext) -> int | None:
    bundle = ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE)
    if bundle is None:
        return None
    profile = getattr(bundle, "profile", None) or {}
    fc = profile.get("followers_count")
    return fc if isinstance(fc, int) else None


def _resolve_media_ref(raw: Any) -> MediaRef | None:
    """Coerce a stored artifact value to a MediaRef, or return None."""
    if isinstance(raw, MediaRef):
        return raw
    if isinstance(raw, dict):
        try:
            return MediaRef(**raw)
        except Exception:
            return None
    return None


def _hydrate_media(
    ref: MediaRef,
    media_repo: MediaAssetRepository,
) -> tuple[bytes, str, str] | None:
    """Fetch bytes for a MediaRef.  Returns (bytes, mime, kind) or None on failure."""
    try:
        _doc, data = media_repo.hydrate(ref.asset_id)
        return data, ref.mime, ref.kind
    except Exception as exc:
        logger.warning("media hydration failed for asset_id=%s: %s", ref.asset_id, exc)
        return None


def _finalize_with_media(
    deps: PostRunDeps,
    ctx: TickRunContext,
    text: str,
    media: list[tuple[bytes, str, str]],
    *,
    creation_metrics: PostCreationMetrics | None,
    followers_at_post: int | None,
) -> dict[str, Any]:
    """Post the tweet with media and run the same post-publish state management
    as finalize_post (post_tick.py), using post_tweet_with_media instead of
    post_tweet.  Returns a finalize_post-compatible result dict."""
    live = deps.live
    account = live.account
    tick_ctx = live.tick_ctx
    outcomes = PipelineOutcomeRepository()

    try:
        tw_result = live.twitter.post_tweet_with_media(account.account_id, text, media)
    except Exception as exc:
        logger.warning("media post failed for %s: %s", account.account_id, exc)
        outcomes.append(
            account_id=account.account_id,
            phase="finalize_post_with_media",
            status="error",
            reason="publish_failed",
            details={"error": str(exc)},
        )
        release_interval_slot_reservation(tick_ctx, account.account_id)
        release_post_guard(tick_ctx, account.account_id)
        return {"account_id": account.account_id, "error": str(exc)}

    account.posts_total += 1
    if tick_ctx.mode == "scheduled":
        account.last_interval_slot = tick_ctx.slot
    account.last_post_id = str(tw_result.get("id") or "")
    account.last_post_text = str(tw_result.get("text") or text)
    account.last_post_at = tick_ctx.now_iso

    record_copied_reference(account, None)

    if tick_ctx.post_registry:
        try:
            tick_ctx.post_registry.record_post(
                account.account_id,
                account.last_post_id,
                tick_ctx.now_iso,
                creation_metrics=creation_metrics,
                followers_at_post=followers_at_post,
            )
            OutcomeLedgerRepository().stamp(
                account_id=account.account_id,
                post_id=account.last_post_id,
                run_id=creation_metrics.run_id if creation_metrics else None,
                soul_hash=creation_metrics.voice_version_hash if creation_metrics else None,
                pipeline_hash=creation_metrics.pipeline_hash if creation_metrics else None,
            )
            m = tick_ctx.twitter.get_tweet_metrics(account.account_id, account.last_post_id)
            imp = m.get("impression_count")
            if isinstance(imp, int):
                account.last_post_views = imp
            if m.get("tweet_permalink") or m.get("media_types") or m.get("embed_urls"):
                tick_ctx.post_registry.update_enrichment(account.account_id, account.last_post_id, m)
        except Exception as exc:
            logger.warning("post-registry / metrics priming failed: %s", exc)

    tick_ctx.repo.save(account)
    try:
        take_snapshot(
            account.account_id,
            refresh_from_x=True,
            repo=tick_ctx.repo,
            post_registry=tick_ctx.post_registry,
        )
    except Exception as exc:
        logger.warning("account snapshot failed for %s: %s", account.account_id, exc)

    finalize_interval_slot_reservation(tick_ctx, account.account_id)
    release_post_guard(tick_ctx, account.account_id)

    out: dict[str, Any] = {
        "account_id": account.account_id,
        "tweet": tw_result,
        "media_ids": tw_result.get("media_ids", []),
    }
    if creation_metrics is not None:
        out["creation_metrics"] = creation_metrics.model_dump(exclude_none=True)
    outcomes.append(account_id=account.account_id, phase="finalize_post_with_media", status="ok")
    return out


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    account = live.account

    composed = ctx.get_artifact(ArtifactKey.COMPOSED_POST_WITH_MEDIA)
    if composed is None:
        reason = "no_composed_post_with_media"
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "posted": False, "skipped_reason": reason},
        )
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    # Accept both model instances and plain dicts.
    if isinstance(composed, dict):
        text: str = composed.get("text", "")
        media_keys: list[str] = composed.get("media_keys") or []
    else:
        text = getattr(composed, "text", "")
        media_keys = list(getattr(composed, "media_keys", None) or [])

    if not text.strip():
        reason = "empty_text"
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "posted": False, "skipped_reason": reason},
        )
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    # Idempotency check.
    idem_key = f"{live.run_id}:{account.account_id}"
    ledger_key = (live.run_id, account.account_id)
    if ledger_key in _POSTED:
        replay_id = _POSTED[ledger_key]
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {
                "account_id": account.account_id,
                "tweet_id": replay_id,
                "posted": True,
                "idempotency_key": idem_key,
                "note": "idempotent_replay",
                "result": {"account_id": account.account_id, "tweet": {"id": replay_id},
                           "note": "idempotent_replay"},
            },
        )
        return StepResult(ok=True, payload={"idempotent_replay": True})

    # Resolve and hydrate media artifacts.
    media_repo = deps.media_repo or MediaAssetRepository()
    media_list: list[tuple[bytes, str, str]] = []
    for key in media_keys:
        artifact_key = _MEDIA_ARTIFACT_KEYS.get(key)
        if artifact_key is None:
            logger.warning("publish_post_with_media: unknown media_key %r, skipping", key)
            continue
        raw = ctx.get_artifact(artifact_key)
        if raw is None:
            logger.warning("publish_post_with_media: artifact %r is absent, skipping", key)
            continue
        ref = _resolve_media_ref(raw)
        if ref is None:
            logger.warning("publish_post_with_media: cannot coerce %r to MediaRef, skipping", key)
            continue
        hydrated = _hydrate_media(ref, media_repo)
        if hydrated is None:
            continue
        media_list.append(hydrated)

    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        tweets_pulled=0,
        tweets_pulled_new=0,
        tweets_pulled_duplicates=0,
        regeneration_round=0,
        source_reference_tweet_id=None,
        chosen_embed_url=None,
        voice_version_hash=account.voice_version_hash,
        voice_version_seq=account.voice_version_seq,
        voice_version_label=account.voice_version_label,
        source_reference_metrics_at_pick=None,
        run_id=live.run_id,
        pipeline_hash=live.pipeline_hash,
    )

    result = _finalize_with_media(
        deps,
        ctx,
        text,
        media_list,
        creation_metrics=creation_metrics,
        followers_at_post=_followers_at_post(ctx),
    )

    tweet_id: str | None = None
    tw = result.get("tweet") if isinstance(result, dict) else None
    if isinstance(tw, dict):
        tweet_id = str(tw.get("id") or "") or None
    if tweet_id and "error" not in result:
        _POSTED[ledger_key] = tweet_id

    media_ids: list[str] = result.get("media_ids") or []

    ctx.set_artifact(
        ArtifactKey.PUBLISHED_POST,
        {
            "account_id": account.account_id,
            "tweet_id": tweet_id,
            "text": text,
            "media_ids": media_ids,
            "posted": "error" not in result,
            "idempotency_key": idem_key,
            "skipped_reason": str(result.get("error")) if "error" in result else None,
            "pipeline_id": ctx.data.get("_pipeline_id", "") if hasattr(ctx, "data") else "",
            "pipeline_weight_at_post": (
                ctx.data.get("_pipeline_weight", 0.0) if hasattr(ctx, "data") else 0.0
            ),
            "result": result,
        },
    )

    if "error" in result:
        return StepResult(ok=False, skip_reason=str(result.get("error")), payload=result)
    return StepResult(ok=True, payload=result)

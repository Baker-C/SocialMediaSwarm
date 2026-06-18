"""Coarse publish tool: wraps finalize_post with an idempotency marker so a retry
cannot double-post to X. Writes PUBLISHED_POST. Reads COMPOSED_POST + SAFETY_VERDICT."""

from __future__ import annotations

import logging

from app.interval.orchestration.post_tick import finalize_post
from app.models.tracked_post import PostCreationMetrics
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

TOOL_ID = "data.publish_post"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Publish the approved post to X (idempotent) and finalize account/registry state"
TOOL_READS = (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)
TOOL_WRITES = (ArtifactKey.PUBLISHED_POST,)

# Process-local idempotency ledger: (run_id, account_id) → tweet_id already posted.
_POSTED: dict[tuple[str, str], str] = {}


def _followers_at_post(ctx: TickRunContext) -> int | None:
    """CC-7: read followers_count from the ACCOUNT_BUNDLE artifact at publish time
    (it is unknown when the runner builds ActLive, pre-walk). Mirrors the imperative
    runner's bundle_account['profile']['followers_count'] read (runner.py:249-253)."""
    bundle = ctx.get_artifact(ArtifactKey.ACCOUNT_BUNDLE)
    if bundle is None:
        return None
    profile = getattr(bundle, "profile", None) or {}
    fc = profile.get("followers_count")
    return fc if isinstance(fc, int) else None


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    account = live.account
    verdict = ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)
    composed = ctx.get_artifact(ArtifactKey.COMPOSED_POST)

    if verdict is None or not verdict.approved or composed is None:
        reason = (verdict.last_reject if verdict else None) or "no_approved_body"
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "posted": False, "skipped_reason": reason},
        )
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    idem_key = f"{live.run_id}:{account.account_id}"
    ledger_key = (live.run_id, account.account_id)
    if ledger_key in _POSTED:
        # A retry within the same run already posted; never double-post. Reconstruct a
        # minimal legacy-shaped result so the runner's _result_from_run still sees a
        # `tweet` object (07 §2.6 reads PUBLISHED_POST.result).
        replay_id = _POSTED[ledger_key]
        ctx.set_artifact(
            ArtifactKey.PUBLISHED_POST,
            {"account_id": account.account_id, "tweet_id": replay_id,
             "posted": True, "idempotency_key": idem_key, "note": "idempotent_replay",
             "regeneration_round": composed.regeneration_round,
             "result": {"account_id": account.account_id, "tweet": {"id": replay_id},
                        "regeneration_round": composed.regeneration_round,
                        "note": "idempotent_replay"}},
        )
        return StepResult(ok=True, payload={"idempotent_replay": True})

    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        tweets_pulled=composed.tweets_pulled,
        tweets_pulled_new=composed.tweets_pulled_new,
        tweets_pulled_duplicates=composed.tweets_pulled_duplicates,
        regeneration_round=composed.regeneration_round,
        source_reference_tweet_id=composed.source_reference_tweet_id,
        chosen_embed_url=composed.chosen_embed_url,
        voice_version_hash=account.voice_version_hash,
        voice_version_seq=account.voice_version_seq,
        voice_version_label=account.voice_version_label,
        source_reference_metrics_at_pick=composed.source_reference_metrics_at_pick,
        # Attribution join (the fields 02 adds to PostCreationMetrics). run_id is the
        # dispatcher run id threaded onto ActLive; pipeline_hash is the LOADED champion
        # spec's version_hash (NOT account.pipeline_version_hash — that accessor does
        # not exist). HARD PREREQ: 02's field add must be merged first, else these two
        # kwargs raise (extra field). See §5.2 Attribution note below.
        run_id=live.run_id,
        pipeline_hash=live.pipeline_hash,
    )

    result = finalize_post(
        live.tick_ctx,
        account,
        composed.body,
        regeneration_round=composed.regeneration_round,
        earlier_reject=verdict.last_reject,
        creation_metrics=creation_metrics,
        source_reference_tweet_id=composed.source_reference_tweet_id,
        followers_at_post=_followers_at_post(ctx),   # CC-7: from ACCOUNT_BUNDLE, not deps.live
    )

    tweet_id = None
    tw = result.get("tweet") if isinstance(result, dict) else None
    if isinstance(tw, dict):
        tweet_id = str(tw.get("id") or "") or None
    if tweet_id and "error" not in result:
        _POSTED[ledger_key] = tweet_id

    ctx.set_artifact(
        ArtifactKey.PUBLISHED_POST,
        {
            "account_id": account.account_id,
            "tweet_id": tweet_id,
            "posted": "error" not in result,
            "regeneration_round": composed.regeneration_round,
            "idempotency_key": idem_key,
            "note": result.get("note"),
            "skipped_reason": str(result.get("error")) if "error" in result else None,
            "result": result,                 # the FULL finalize_post dict — runner returns this
        },
    )
    if "error" in result:
        return StepResult(ok=False, skip_reason=str(result.get("error")), payload=result)
    return StepResult(ok=True, payload=result)

"""Coarse reply-publish tool: publish the drafted reply in-reply-to the mention (doc 12).

Reads REPLY_DRAFT + REPLY_VERDICT; writes REPLY_RESULT.
"""

from __future__ import annotations

from app.interval.orchestration.reply_tick import finalize_reply
from app.models.tracked_post import PostCreationMetrics
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "data.reply_publish"
TOOL_KIND = "data"
TOOL_SOURCE = "x_api"
TOOL_PURPOSE = "Publish the approved reply in-reply-to the mention (idempotent)"
TOOL_READS = (ArtifactKey.REPLY_DRAFT, ArtifactKey.REPLY_VERDICT)
TOOL_WRITES = (ArtifactKey.REPLY_RESULT,)

# Process-local idempotency ledger: (run_id, in_reply_to_tweet_id) -> reply tweet id
_POSTED: dict[tuple[str, str], str] = {}


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    account = live.account
    verdict = ctx.get_artifact(ArtifactKey.REPLY_VERDICT)
    draft = ctx.get_artifact(ArtifactKey.REPLY_DRAFT)

    if verdict is None or getattr(verdict, "decision", None) != "reply" or draft is None:
        reason = getattr(verdict, "reason", None) or "no_reply_decision"
        ctx.set_artifact(
            ArtifactKey.REPLY_RESULT,
            {
                "account_id": account.account_id,
                "posted": False,
                "skipped_reason": reason,
            },
        )
        return StepResult(ok=True, skipped=True, skip_reason=reason)

    target = draft.in_reply_to_tweet_id
    ledger_key = (live.run_id, target)
    if ledger_key in _POSTED:  # never double-reply on a same-run retry
        ctx.set_artifact(
            ArtifactKey.REPLY_RESULT,
            {
                "account_id": account.account_id,
                "tweet_id": _POSTED[ledger_key],
                "in_reply_to_tweet_id": target,
                "posted": True,
                "note": "idempotent_replay",
            },
        )
        return StepResult(ok=True, payload={"idempotent_replay": True})

    creation_metrics = PostCreationMetrics(
        candidates_created=1,
        regeneration_round=draft.regeneration_round,
        source_reference_tweet_id=target,
        voice_version_hash=account.voice_version_hash,
        voice_version_seq=account.voice_version_seq,
        voice_version_label=account.voice_version_label,
        run_id=live.run_id,
        pipeline_hash=live.pipeline_hash,
    )
    result = finalize_reply(
        live.tick_ctx,
        account,
        draft.body,
        in_reply_to_tweet_id=target,
        target_author_handle=draft.target_author_handle,
        creation_metrics=creation_metrics,
    )
    tweet_id = (result.get("tweet") or {}).get("id") if isinstance(result, dict) else None
    if tweet_id and "error" not in result:
        _POSTED[ledger_key] = tweet_id
    ctx.set_artifact(
        ArtifactKey.REPLY_RESULT,
        {
            "account_id": account.account_id,
            "tweet_id": tweet_id,
            "in_reply_to_tweet_id": target,
            "posted": "error" not in result,
            "note": result.get("note"),
        },
    )
    if "error" in result:
        return StepResult(
            ok=False, skip_reason=str(result.get("error")), payload=result
        )
    return StepResult(ok=True, payload=result)

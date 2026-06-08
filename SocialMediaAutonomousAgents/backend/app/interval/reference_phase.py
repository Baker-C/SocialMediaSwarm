"""Bridge interval tick context → pipeline reference runbook (single analysis path)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.interval.tweet_topic_preanalysis import (
    GatheredTweet,
    reference_pool_skip_reason,
)
from app.models.account import AccountDocument
from app.pipeline._runbook_engine import RunbookResult, run_steps
from app.pipeline.runbook import start
from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
from app.pipeline.services.deps import PostRunDeps
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository

if TYPE_CHECKING:
    from app.interval.context import TickContext


@dataclass
class ReferencePhaseResult:
    ok: bool
    skip_reason: str | None = None
    bundle_account: dict[str, Any] = field(default_factory=dict)
    refs_payload: dict[str, Any] = field(default_factory=dict)
    reference_pool: list[dict[str, Any]] = field(default_factory=list)
    ranked_refs: list[GatheredTweet] = field(default_factory=list)
    timeline_analysis: dict[str, Any] | None = None
    own_posts_analysis: dict[str, Any] | None = None
    runbook: RunbookResult | None = None


def post_run_deps_from_tick(tick_ctx: TickContext) -> PostRunDeps:
    """Reuse services already wired on the interval tick (no duplicate TickDataService)."""
    return PostRunDeps(
        tick_data=tick_ctx.tick_data,
        repo=tick_ctx.repo,
        post_registry=tick_ctx.post_registry,
        twitter=tick_ctx.twitter,
    )


def ranked_refs_from_runbook(
    run_ctx_data: dict[str, Any],
    *,
    copied_exclude: frozenset[str],
) -> list[GatheredTweet]:
    ranked_payload = run_ctx_data.get("timeline_ranked") or {}
    ranked_raw = ranked_payload.get("ranked") if isinstance(ranked_payload, dict) else []
    out: list[GatheredTweet] = []
    for row in ranked_raw or []:
        if not isinstance(row, dict):
            continue
        gt = GatheredTweet.model_validate(row)
        if gt.tweet_id in copied_exclude:
            continue
        out.append(gt)
    max_attempts = max(0, int(settings.max_reference_fallback_attempts))
    if max_attempts > 0:
        out = out[:max_attempts]
    return out


def run_reference_phase(
    tick_ctx: TickContext,
    account: AccountDocument,
    *,
    copied_exclude: frozenset[str],
) -> ReferencePhaseResult:
    outcomes = PipelineOutcomeRepository()
    """Run the pipeline reference runbook (profile → pools → dual analysis)."""
    run_ctx = start(
        account.account_id,
        niche=account.niche,
        mode=tick_ctx.mode,
        slot=tick_ctx.slot,
    )
    deps = post_run_deps_from_tick(tick_ctx)
    runbook_result = run_steps(POST_TICK_REFERENCE_STEPS, run_ctx, deps)

    bundle_account = dict(run_ctx.get("account_bundle") or {})
    refs_payload = dict(run_ctx.get("timeline_references") or {})
    timeline_analysis = run_ctx.get("timeline_analysis")
    own_posts_analysis = run_ctx.get("own_posts_analysis")

    bundle_account["timeline_reference_tweets"] = refs_payload.get("timeline_reference_tweets") or []
    bundle_account["reference_errors"] = refs_payload.get("reference_errors") or []
    if isinstance(timeline_analysis, dict):
        bundle_account["timeline_analysis"] = timeline_analysis
    if isinstance(own_posts_analysis, dict):
        bundle_account["own_posts_analysis"] = own_posts_analysis

    reference_pool = filter_rows_with_urls(TickDataService.merge_reference_pool(refs_payload))

    if isinstance(timeline_analysis, dict) and timeline_analysis.get("skipped"):
        skip = str(timeline_analysis.get("skip_reason") or "no_reference_with_urls")
        outcomes.append(
            account_id=account.account_id,
            phase="reference_phase",
            status="skipped",
            reason=skip,
        )
        return ReferencePhaseResult(
            ok=False,
            skip_reason=skip,
            bundle_account=bundle_account,
            refs_payload=refs_payload,
            reference_pool=reference_pool,
            timeline_analysis=timeline_analysis,
            own_posts_analysis=own_posts_analysis if isinstance(own_posts_analysis, dict) else None,
            runbook=runbook_result,
        )

    ranked_refs = ranked_refs_from_runbook(run_ctx.data, copied_exclude=copied_exclude)
    if not ranked_refs:
        pool_skip = reference_pool_skip_reason(reference_pool, exclude_ids=copied_exclude)
        skip = pool_skip or "no_ranked_references"
        outcomes.append(
            account_id=account.account_id,
            phase="reference_phase",
            status="skipped",
            reason=skip,
        )
        return ReferencePhaseResult(
            ok=False,
            skip_reason=skip,
            bundle_account=bundle_account,
            refs_payload=refs_payload,
            reference_pool=reference_pool,
            timeline_analysis=timeline_analysis if isinstance(timeline_analysis, dict) else None,
            own_posts_analysis=own_posts_analysis if isinstance(own_posts_analysis, dict) else None,
            runbook=runbook_result,
        )

    outcomes.append(account_id=account.account_id, phase="reference_phase", status="ok")
    return ReferencePhaseResult(
        ok=True,
        bundle_account=bundle_account,
        refs_payload=refs_payload,
        reference_pool=reference_pool,
        ranked_refs=ranked_refs,
        timeline_analysis=timeline_analysis if isinstance(timeline_analysis, dict) else None,
        own_posts_analysis=own_posts_analysis if isinstance(own_posts_analysis, dict) else None,
        runbook=runbook_result,
    )

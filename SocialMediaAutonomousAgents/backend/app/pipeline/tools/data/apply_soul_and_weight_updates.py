"""Apply niche score and pipeline weight updates to all accounts (terminal)."""

from __future__ import annotations

from typing import Any

from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.account_repository import AccountRepository
from app.services.pipeline_spec_repository import PipelineSpecRepository

TOOL_ID = "data.apply_soul_and_weight_updates"
TOOL_KIND = "data"
TOOL_PURPOSE = "Apply niche score and pipeline weight updates to all accounts (terminal)"
TOOL_READS = (ArtifactKey.NICHE_WEIGHT_PROPOSALS, ArtifactKey.PIPELINE_WEIGHT_PROPOSALS)
TOOL_WRITES = (ArtifactKey.UPDATES_APPLIED,)


def run(
    ctx: TickRunContext,
    *,
    account_repo: AccountRepository | None = None,
    pipeline_repo: PipelineSpecRepository | None = None,
) -> StepResult:
    niche_proposals: dict[str, dict[str, Any]] = ctx.get("niche_weight_proposals") or {}
    pipeline_proposals: dict[str, dict[str, Any]] = ctx.get("pipeline_weight_proposals") or {}
    result = apply(
        niche_weight_proposals=niche_proposals,
        pipeline_weight_proposals=pipeline_proposals,
        account_repo=account_repo,
        pipeline_repo=pipeline_repo,
    )
    ctx.set("updates_applied", result)
    return StepResult(ok=True, payload=result)


def apply(
    *,
    niche_weight_proposals: dict[str, dict[str, Any]],
    pipeline_weight_proposals: dict[str, dict[str, Any]],
    account_repo: AccountRepository | None = None,
    pipeline_repo: PipelineSpecRepository | None = None,
) -> dict[str, Any]:
    """Apply proposals and return a summary of how many accounts/pipelines were updated."""
    acc_repo = account_repo or AccountRepository()
    pipe_repo = pipeline_repo or PipelineSpecRepository()

    accounts_updated = 0
    pipelines_updated = 0
    errors: list[str] = []

    # ── niche score updates ──
    for account_id, niche_scores in niche_weight_proposals.items():
        if not niche_scores:
            continue
        try:
            doc = acc_repo.load(account_id)
            if doc is None:
                errors.append(f"account not found: {account_id}")
                continue
            changed = False
            for niche_id, new_score in niche_scores.items():
                for niche in doc.soul.niches:
                    if niche.niche == niche_id:
                        niche.score = int(new_score)
                        changed = True
                        break
            if changed:
                acc_repo.save(doc)
                accounts_updated += 1
        except Exception as exc:
            errors.append(f"niche update failed for {account_id}: {exc}")

    # ── pipeline weight updates ──
    for account_id, weight_map in pipeline_weight_proposals.items():
        if not weight_map:
            continue
        for pipeline_name, new_weight in weight_map.items():
            try:
                spec = pipe_repo.load(account_id, status="champion")
                if spec is None:
                    errors.append(f"pipeline spec not found for {account_id}")
                    continue
                spec.weight = float(new_weight)
                pipe_repo.save(spec)
                pipelines_updated += 1
            except Exception as exc:
                errors.append(f"pipeline weight update failed for {account_id}/{pipeline_name}: {exc}")

    result: dict[str, Any] = {
        "accounts_updated": accounts_updated,
        "pipelines_updated": pipelines_updated,
    }
    if errors:
        result["errors"] = errors
    return result

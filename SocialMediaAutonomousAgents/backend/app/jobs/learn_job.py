"""LEARN tick: per active account, auto-rollback hard regressions, optionally auto-promote,
and stage challengers. Pure RavenDB reads/writes — NO X-API calls."""

import logging

from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.services.champion_challenger_service import (
    evaluate_promotion,
    evaluate_regression,
)
from app.services.pipeline_spec_repository import PipelineSpecRepository, promote_challenger
from app.services.spec_rewrite_service import propose_and_stage_challenger
from app.services.spec_rollback import rollback_to_parent

logger = logging.getLogger(__name__)


def run_learn_job() -> dict:
    """LEARN tick: per active account, (1) auto-rollback a hard-regressed champion,
    (2) optionally auto-promote an improved challenger, (3) stage a challenger if none
    exists. Pure RavenDB reads/writes — NO X-API calls."""
    if not settings.learn_enabled:
        return {"skipped": "learn_disabled"}
    accounts = AccountRepository().list_active()
    repo = PipelineSpecRepository()
    actions: list[dict] = []
    for acc in accounts:
        aid = acc.account_id
        champ = repo.load(aid, "champion")
        if champ is None:
            continue  # no spec yet (pre-seed) → nothing to learn from

        # (1) auto-rollback on hard regression (the ONE automatic mutation)
        if settings.learn_auto_rollback_enabled and champ.parent_hash:
            reg = evaluate_regression(
                aid,
                current_hash=champ.version_hash,
                parent_hash=champ.parent_hash,
                min_window=settings.learn_rollback_min_window,
                hard_drop=settings.learn_rollback_hard_drop,
            )
            if reg.regressed:
                restored = rollback_to_parent(aid, parent_hash=champ.parent_hash, repo=repo)
                actions.append(
                    {
                        "account_id": aid,
                        "action": "rollback",
                        "drop": reg.drop,
                        "ok": restored is not None,
                    }
                )
                logger.info(
                    "learn_job: rolled back %s (drop=%.3f, ok=%s)",
                    aid,
                    reg.drop or 0.0,
                    restored is not None,
                )
                continue  # rolled back this tick; do not also stage/promote on the same pass

        # (2) optional auto-promote (default OFF → manual)
        challenger = repo.load(aid, "challenger")
        if challenger is not None and settings.learn_auto_promote_enabled:
            verdict = evaluate_promotion(
                aid,
                champion_hash=champ.version_hash,
                challenger_hash=challenger.version_hash,
                min_window=settings.learn_promote_min_window,
                min_improvement=settings.learn_promote_min_improvement,
            )
            if verdict.eligible:
                promote_challenger(aid, repo=repo)
                actions.append(
                    {"account_id": aid, "action": "promote", "delta": verdict.delta}
                )
                logger.info("learn_job: promoted %s (delta=%.3f)", aid, verdict.delta or 0.0)
                continue

        # (3) stage a challenger when there is none to compare against
        if challenger is None and settings.learn_propose_challenger_enabled:
            staged = propose_and_stage_challenger(aid, repo=repo)
            actions.append(
                {"account_id": aid, "action": "stage_challenger", "staged": staged is not None}
            )
            if staged:
                logger.info("learn_job: staged challenger for %s", aid)

    logger.info("learn_job: %d accounts, %d actions", len(accounts), len(actions))
    return {"accounts": len(accounts), "actions": actions, "status": "ok"}

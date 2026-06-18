"""Champion/challenger scoring and decision rules for the interpreter LEARN loop."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.outcome_ledger_repository import OutcomeLedgerRepository


@dataclass(frozen=True)
class SpecScore:
    """Aggregated reward for a single spec version (pipeline or soul hash)."""

    pipeline_hash: str
    n_scored: int  # rows with a non-None reward (the comparison sample size)
    n_total: int  # rows that exist (scored + still-None/unpolled)
    avg_reward: float | None  # mean of the non-None rewards, or None if n_scored == 0


def score_pipeline_hash(
    pipeline_hash: str,
    *,
    account_id: str,
    limit: int = 500,
    ledger: OutcomeLedgerRepository | None = None,
) -> SpecScore:
    """Mean reward over the ledger rows attributed to one pipeline version.
    None rewards (post not yet polled) are EXCLUDED from the average and counted
    separately, never treated as 0."""
    ledger = ledger or OutcomeLedgerRepository()
    rows = ledger.list_for_pipeline_hash(pipeline_hash, account_id=account_id, limit=limit)
    scored = [r.reward for r in rows if isinstance(r.reward, (int, float))]
    return SpecScore(
        pipeline_hash=pipeline_hash,
        n_scored=len(scored),
        n_total=len(rows),
        avg_reward=(sum(scored) / len(scored)) if scored else None,
    )


def score_soul_hash(
    soul_hash: str,
    *,
    account_id: str,
    limit: int = 500,
    ledger: OutcomeLedgerRepository | None = None,
) -> SpecScore:
    """Mean reward over the ledger rows attributed to one soul version.
    Mirror of score_pipeline_hash for soul A/B scoring."""
    ledger = ledger or OutcomeLedgerRepository()
    rows = ledger.list_for_soul_hash(soul_hash, account_id=account_id, limit=limit)
    scored = [r.reward for r in rows if isinstance(r.reward, (int, float))]
    return SpecScore(
        pipeline_hash=soul_hash,  # reuse the dataclass; caller knows it's a soul hash
        n_scored=len(scored),
        n_total=len(rows),
        avg_reward=(sum(scored) / len(scored)) if scored else None,
    )


@dataclass(frozen=True)
class PromotionVerdict:
    """Recommendation: is the challenger eligible for promotion?"""

    eligible: bool
    reason: str  # "insufficient_window" | "no_improvement" | "improved"
    champion: SpecScore
    challenger: SpecScore
    delta: float | None  # challenger.avg_reward - champion.avg_reward, or None


def evaluate_promotion(
    account_id: str,
    *,
    champion_hash: str,
    challenger_hash: str,
    min_window: int,
    min_improvement: float,
    ledger: OutcomeLedgerRepository | None = None,
) -> PromotionVerdict:
    """Compare champion vs challenger reward. Returns eligible=True only when
    both arms have a minimum scored sample and the challenger's delta meets
    the improvement threshold."""
    champ = score_pipeline_hash(champion_hash, account_id=account_id, ledger=ledger)
    chal = score_pipeline_hash(challenger_hash, account_id=account_id, ledger=ledger)

    # Both arms need a minimum scored sample, else we have no signal.
    if champ.n_scored < min_window or chal.n_scored < min_window:
        return PromotionVerdict(False, "insufficient_window", champ, chal, None)

    delta = (chal.avg_reward or 0.0) - (champ.avg_reward or 0.0)
    if delta >= min_improvement:
        return PromotionVerdict(True, "improved", champ, chal, delta)
    return PromotionVerdict(False, "no_improvement", champ, chal, delta)


@dataclass(frozen=True)
class RegressionVerdict:
    """Regression check: did the current champion regress vs its parent?"""

    regressed: bool
    reason: str  # "no_parent" | "insufficient_window" | "stable" | "hard_regression"
    current: SpecScore
    parent: SpecScore | None
    drop: float | None  # parent.avg_reward - current.avg_reward, or None


def evaluate_regression(
    account_id: str,
    *,
    current_hash: str,
    parent_hash: str | None,
    min_window: int,
    hard_drop: float,
    ledger: OutcomeLedgerRepository | None = None,
) -> RegressionVerdict:
    """Check if a champion has hard-regressed vs its parent. Returns regressed=True
    only when the parent out-scores the current champion by >= hard_drop on a
    sufficient sample."""
    if not parent_hash:
        return RegressionVerdict(
            False, "no_parent", score_pipeline_hash(current_hash, account_id=account_id, ledger=ledger), None, None
        )
    cur = score_pipeline_hash(current_hash, account_id=account_id, ledger=ledger)
    par = score_pipeline_hash(parent_hash, account_id=account_id, ledger=ledger)
    if cur.n_scored < min_window or par.n_scored < min_window:
        return RegressionVerdict(False, "insufficient_window", cur, par, None)
    drop = (par.avg_reward or 0.0) - (cur.avg_reward or 0.0)
    if drop >= hard_drop:
        return RegressionVerdict(True, "hard_regression", cur, par, drop)
    return RegressionVerdict(False, "stable", cur, par, drop)

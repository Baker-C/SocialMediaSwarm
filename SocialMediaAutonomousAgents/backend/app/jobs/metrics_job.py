import logging
from datetime import datetime, timezone

from app.models.metrics import AccountMetricsDocument
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.post_registry import TrackedPostRepository
from app.infrastructure.ravendb_http import get_ravendb_client
from app.services.account_repository import AccountRepository

logger = logging.getLogger(__name__)


def run_metrics_job() -> dict:
    """Compute per-account metric aggregates and persist AccountMetrics."""
    repo = AccountRepository()
    trepo = TrackedPostRepository()
    outcomes = PipelineOutcomeRepository()
    client = get_ravendb_client()
    active = repo.list_active()
    n = len(active)
    updated = 0
    for acc in active:
        rows = trepo.list_for_account(acc.account_id)
        engagement_rates = [r.get("engagement_rate") for r in rows if isinstance(r.get("engagement_rate"), (int, float))]
        reply_rates = [r.get("reply_rate") for r in rows if isinstance(r.get("reply_rate"), (int, float))]
        like_rates = [r.get("like_rate") for r in rows if isinstance(r.get("like_rate"), (int, float))]
        deltas = [r.get("follower_delta") for r in rows if isinstance(r.get("follower_delta"), int)]
        pos_eng = [
            r.get("engagement_rate")
            for r in rows
            if isinstance(r.get("engagement_rate"), (int, float)) and isinstance(r.get("follower_delta"), int) and r.get("follower_delta") > 0
        ]
        non_pos_eng = [
            r.get("engagement_rate")
            for r in rows
            if isinstance(r.get("engagement_rate"), (int, float))
            and isinstance(r.get("follower_delta"), int)
            and r.get("follower_delta") <= 0
        ]
        doc = AccountMetricsDocument(
            account_id=acc.account_id,
            computed_at=datetime.now(timezone.utc).isoformat(),
            avg_engagement_rate=_avg(engagement_rates),
            avg_reply_rate=_avg(reply_rates),
            avg_like_rate=_avg(like_rates),
            avg_follower_delta=_avg(deltas),
            positive_delta_avg_engagement=_avg(pos_eng),
            non_positive_delta_avg_engagement=_avg(non_pos_eng),
            follower_delta_engagement_gap=_gap(_avg(pos_eng), _avg(non_pos_eng)),
        )
        client.put_document(
            AccountMetricsDocument.document_id(acc.account_id),
            doc.model_dump(exclude_none=True),
            collection="AccountMetrics",
        )
        outcomes.append(account_id=acc.account_id, phase="metrics_job", status="ok")
        updated += 1
    logger.debug("metrics_job: %d active accounts", n)
    return {"active_accounts": n, "updated": updated, "status": "ok"}


def _avg(values: list[int | float]) -> float | None:
    if not values:
        return None
    return float(sum(float(v) for v in values)) / float(len(values))


def _gap(pos: float | None, non_pos: float | None) -> float | None:
    if pos is None or non_pos is None:
        return None
    return float(pos) - float(non_pos)

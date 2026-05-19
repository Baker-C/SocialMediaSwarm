import logging

from app.services.account_repository import AccountRepository

logger = logging.getLogger(__name__)


def run_metrics_job() -> dict:
    """Placeholder for hourly AccountMetrics batch."""
    repo = AccountRepository()
    n = len(repo.list_active())
    logger.debug("metrics_job: %d active accounts", n)
    return {"active_accounts": n, "status": "placeholder"}

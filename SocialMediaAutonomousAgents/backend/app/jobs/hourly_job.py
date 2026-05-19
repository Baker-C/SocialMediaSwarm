import logging

from app.agents.orchestrator import Orchestrator
from app.core.config import settings

logger = logging.getLogger(__name__)


def run_hourly_job() -> dict:
    """Scheduled posting tick: one pass per active account in RavenDB."""
    if not settings.hourly_posting_enabled:
        logger.info("hourly_job skipped (HOURLY_POSTING_ENABLED=false)")
        return {"slot": None, "results": [], "skipped": "hourly_posting_disabled"}
    try:
        result = Orchestrator().run_tick()
        logger.info("hourly_job slot=%s accounts=%s", result.get("slot"), len(result.get("results", [])))
        return result
    except Exception:
        logger.exception("hourly_job failed")
        raise

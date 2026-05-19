import logging

from app.agents.orchestrator import Orchestrator, TickRunMode
from app.core.config import settings

logger = logging.getLogger(__name__)


def _scheduler_tick_mode() -> TickRunMode:
    mode = (settings.scheduler_post_mode or "scheduled").strip().lower()
    if mode == "force":
        return "force"
    if mode != "scheduled":
        logger.warning("Unknown SCHEDULER_POST_MODE=%s; using scheduled", settings.scheduler_post_mode)
    return "scheduled"


def run_hourly_job() -> dict:
    """Scheduled posting tick: all active accounts on POST_INTERVAL_MINUTES cadence."""
    if not settings.hourly_posting_enabled:
        logger.info("hourly_job skipped (HOURLY_POSTING_ENABLED=false)")
        return {"slot": None, "results": [], "skipped": "hourly_posting_disabled"}
    mode = _scheduler_tick_mode()
    bypass = bool(settings.scheduler_bypass_cooldown)
    try:
        result = Orchestrator().run_tick(mode=mode, bypass_post_cooldown=bypass)
        logger.info(
            "hourly_job mode=%s bypass_cooldown=%s slot=%s accounts=%s",
            mode,
            bypass,
            result.get("slot"),
            len(result.get("results", [])),
        )
        return result
    except Exception:
        logger.exception("hourly_job failed (mode=%s)", mode)
        raise

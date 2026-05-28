import logging

from app.agents.orchestrator import Orchestrator, TickRunMode
from app.core.config import settings
from app.hourly.orchestration.posting_hours import is_post_quiet_hours, quiet_hours_skip_reason

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
    if is_post_quiet_hours():
        reason = quiet_hours_skip_reason() or "quiet_hours"
        logger.info(
            "hourly_job skipped (%s; no posts %02d:00–%02d:00 %s)",
            reason,
            settings.post_quiet_hours_start,
            settings.post_quiet_hours_end,
            settings.scheduler_timezone,
        )
        return {"slot": None, "results": [], "skipped": reason}
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

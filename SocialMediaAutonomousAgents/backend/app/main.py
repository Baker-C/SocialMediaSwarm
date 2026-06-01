from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.api.routes import accounts, posts, patterns, metrics, dashboard, health
from app.core.config import settings
from app.infrastructure.scheduler_lock import release_scheduler_lock, try_acquire_scheduler_lock
from app.jobs.engagement_job import run_engagement_job
from app.jobs.interval_job import run_interval_job
from app.jobs.metrics_job import run_metrics_job

logger = logging.getLogger(__name__)


def _posting_trigger(tz: ZoneInfo, interval_minutes: int):
    """Fire on clock-aligned minute marks when possible, else fixed interval from scheduler start."""
    interval_m = max(1, int(interval_minutes))
    if interval_m < 60:
        minute_expr = ",".join(str(m) for m in range(0, 60, interval_m))
        return CronTrigger(minute=minute_expr, timezone=tz)
    logger.warning(
        "POST_INTERVAL_MINUTES=%s >= 60; using interval trigger",
        interval_m,
    )
    return IntervalTrigger(minutes=interval_m, timezone=tz)


def _build_scheduler() -> AsyncIOScheduler:
    try:
        tz = ZoneInfo(settings.scheduler_timezone)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid SCHEDULER_TIMEZONE=%s, falling back to UTC", settings.scheduler_timezone)
        tz = ZoneInfo("UTC")
    sched = AsyncIOScheduler(timezone=tz)
    misfire = settings.scheduler_misfire_grace_seconds
    if settings.interval_posting_enabled:
        interval_m = max(1, int(settings.post_interval_minutes))
        sched.add_job(
            run_interval_job,
            _posting_trigger(tz, interval_m),
            id="scheduled_posting",
            replace_existing=True,
            misfire_grace_time=misfire,
            coalesce=True,
            max_instances=1,
        )
    sched.add_job(
        run_engagement_job,
        CronTrigger(minute="5", timezone=tz),
        id="engagement_poll",
        replace_existing=True,
        misfire_grace_time=misfire,
        coalesce=True,
        max_instances=1,
    )
    sched.add_job(
        run_metrics_job,
        CronTrigger(minute="10", timezone=tz),
        id="metrics_batch",
        replace_existing=True,
        misfire_grace_time=misfire,
        coalesce=True,
        max_instances=1,
    )
    return sched


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    scheduler = None
    if settings.run_scheduler and try_acquire_scheduler_lock():
        scheduler = _build_scheduler()
        scheduler.start()
        if settings.interval_posting_enabled:
            interval_m = max(1, int(settings.post_interval_minutes))
            mode = (settings.scheduler_post_mode or "scheduled").strip().lower()
            cooldown = "bypass cooldown" if settings.scheduler_bypass_cooldown else "respect cooldown"
            if interval_m < 60:
                marks = ",".join(f":{m:02d}" for m in range(0, 60, interval_m))
                posting = f"{mode} posting at {marks} each hour ({settings.scheduler_timezone}, {cooldown})"
            else:
                posting = f"{mode} posting every {interval_m}m ({cooldown})"
            if settings.post_quiet_hours_enabled:
                posting += (
                    f"; paused {settings.post_quiet_hours_start:02d}:00–"
                    f"{settings.post_quiet_hours_end:02d}:00"
                )
        else:
            posting = "posting (disabled)"
        logger.info(
            "APScheduler started (timezone=%s): %s, engagement :05, metrics :10",
            settings.scheduler_timezone,
            posting,
        )
    elif not settings.run_scheduler:
        logger.info("APScheduler disabled (RUN_SCHEDULER=false)")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
    release_scheduler_lock()


app = FastAPI(title="Social Media Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(posts.router, prefix="/api", tags=["posts"])
app.include_router(patterns.router, prefix="/api", tags=["patterns"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])

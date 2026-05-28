"""Wall-clock windows when the scheduler must not post."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


def scheduler_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.scheduler_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def is_post_quiet_hours(now: datetime | None = None) -> bool:
    """
    True when automated posting should pause (inclusive start, exclusive end).

    Default: no posts from 00:00 up to (but not including) 08:00 in ``SCHEDULER_TIMEZONE``.
    Manual ``create_forced_post.py`` runs are not gated here.
    """
    if not settings.post_quiet_hours_enabled:
        return False

    start = int(settings.post_quiet_hours_start)
    end = int(settings.post_quiet_hours_end)
    if start == end:
        return False

    tz = scheduler_timezone()
    t = now if now is not None else datetime.now(tz)
    if t.tzinfo is None:
        t = t.replace(tzinfo=tz)
    else:
        t = t.astimezone(tz)

    hour = t.hour
    if start < end:
        return start <= hour < end
    # Wraps midnight (e.g. 22:00–06:00)
    return hour >= start or hour < end


def quiet_hours_skip_reason() -> str | None:
    if not is_post_quiet_hours():
        return None
    return (
        f"quiet_hours_{settings.post_quiet_hours_start:02d}"
        f"_{settings.post_quiet_hours_end:02d}_{settings.scheduler_timezone}"
    )

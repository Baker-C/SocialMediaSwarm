"""Quiet hours for scheduled posting."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.interval.orchestration.posting_hours import is_post_quiet_hours, quiet_hours_skip_reason
from app.jobs.interval_job import run_interval_job


@patch("app.interval.orchestration.posting_hours.settings")
def test_quiet_hours_midnight_to_8am(mock_settings) -> None:
    mock_settings.post_quiet_hours_enabled = True
    mock_settings.post_quiet_hours_start = 0
    mock_settings.post_quiet_hours_end = 8
    mock_settings.scheduler_timezone = "UTC"
    tz = ZoneInfo("UTC")
    assert is_post_quiet_hours(datetime(2026, 5, 26, 0, 30, tzinfo=tz))
    assert is_post_quiet_hours(datetime(2026, 5, 26, 7, 59, tzinfo=tz))
    assert not is_post_quiet_hours(datetime(2026, 5, 26, 8, 0, tzinfo=tz))
    assert not is_post_quiet_hours(datetime(2026, 5, 26, 23, 0, tzinfo=tz))


@patch("app.interval.orchestration.posting_hours.settings")
def test_quiet_hours_disabled(mock_settings) -> None:
    mock_settings.post_quiet_hours_enabled = False
    tz = ZoneInfo("UTC")
    assert not is_post_quiet_hours(datetime(2026, 5, 26, 3, 0, tzinfo=tz))


def test_interval_job_skips_during_quiet_hours(monkeypatch) -> None:
    monkeypatch.setattr("app.jobs.interval_job.settings.interval_posting_enabled", True)
    monkeypatch.setattr("app.jobs.interval_job.is_post_quiet_hours", lambda: True)
    monkeypatch.setattr(
        "app.jobs.interval_job.quiet_hours_skip_reason",
        lambda: "quiet_hours_00_08_UTC",
    )
    from unittest.mock import MagicMock, patch

    mock_orch = MagicMock()
    with patch("app.jobs.interval_job.Orchestrator", return_value=mock_orch):
        out = run_interval_job()
    mock_orch.run_tick.assert_not_called()
    assert "quiet_hours" in out["skipped"]

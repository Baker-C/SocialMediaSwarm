"""Scheduled post slot idempotency buckets."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.account_repository import current_post_slot_key


@patch("app.services.account_repository.settings")
def test_slot_key_20_minute_buckets(mock_settings) -> None:
    mock_settings.scheduler_timezone = "UTC"
    mock_settings.post_interval_minutes = 20
    tz = ZoneInfo("UTC")
    with patch("app.services.account_repository.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 19, 14, 7, 30, tzinfo=tz)
        assert current_post_slot_key() == "2026-05-19-14-00"
        mock_dt.now.return_value = datetime(2026, 5, 19, 14, 25, 0, tzinfo=tz)
        assert current_post_slot_key() == "2026-05-19-14-20"


@patch("app.services.account_repository.settings")
def test_slot_key_18_minute_buckets(mock_settings) -> None:
    mock_settings.scheduler_timezone = "UTC"
    mock_settings.post_interval_minutes = 18
    tz = ZoneInfo("UTC")
    with patch("app.services.account_repository.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 19, 14, 10, 0, tzinfo=tz)
        assert current_post_slot_key() == "2026-05-19-14-00"
        mock_dt.now.return_value = datetime(2026, 5, 19, 14, 25, 0, tzinfo=tz)
        assert current_post_slot_key() == "2026-05-19-14-18"

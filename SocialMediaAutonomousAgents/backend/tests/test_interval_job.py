"""Scheduler posting job tests."""

from unittest.mock import MagicMock, patch

from app.jobs.interval_job import run_interval_job


def test_run_interval_job_uses_force_mode_with_bypass(monkeypatch) -> None:
    monkeypatch.setattr("app.jobs.interval_job.settings.interval_posting_enabled", True)
    monkeypatch.setattr("app.jobs.interval_job.settings.scheduler_post_mode", "force")
    monkeypatch.setattr("app.jobs.interval_job.settings.scheduler_bypass_cooldown", True)
    mock_orch = MagicMock()
    mock_orch.run_tick.return_value = {"slot": "2026-05-19-23-00", "results": []}
    with patch("app.jobs.interval_job.Orchestrator", return_value=mock_orch):
        run_interval_job()
    mock_orch.run_tick.assert_called_once_with(mode="force", bypass_post_cooldown=True)


def test_run_interval_job_skipped_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.jobs.interval_job.settings.interval_posting_enabled", False)
    mock_orch = MagicMock()
    with patch("app.jobs.interval_job.Orchestrator", return_value=mock_orch):
        out = run_interval_job()
    mock_orch.run_tick.assert_not_called()
    assert out["skipped"] == "interval_posting_disabled"

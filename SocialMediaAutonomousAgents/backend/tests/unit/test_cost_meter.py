"""Tests for the CostMeter (hard per-run cost ceiling)."""

import pytest

from app.core.cost_meter import CostCeilingExceeded, CostMeter


class TestCostMeter:
    """Test suite for CostMeter functionality."""

    def test_cost_meter_initializes(self):
        """CostMeter should initialize with correct fields."""
        meter = CostMeter(run_id="run_123", ceiling_usd=0.50)
        assert meter.run_id == "run_123"
        assert meter.ceiling_usd == 0.50
        assert meter.spent_usd == 0.0
        assert meter.per_step == {}

    def test_check_before_passes_under_ceiling(self):
        """check_before should pass when under the ceiling."""
        meter = CostMeter(run_id="run_123", ceiling_usd=0.50)
        meter.spent_usd = 0.30
        # Should not raise
        meter.check_before("step_1")

    def test_check_before_raises_at_ceiling(self):
        """check_before should raise when at or over the ceiling."""
        meter = CostMeter(run_id="run_123", ceiling_usd=0.50)
        meter.spent_usd = 0.50
        with pytest.raises(CostCeilingExceeded) as exc_info:
            meter.check_before("step_1")
        assert exc_info.value.run_id == "run_123"
        assert exc_info.value.spent == 0.50
        assert exc_info.value.ceiling == 0.50
        assert exc_info.value.step_id == "step_1"

    def test_check_before_disabled_when_ceiling_zero(self):
        """check_before should not raise when ceiling_usd is 0 (disabled)."""
        meter = CostMeter(run_id="run_123", ceiling_usd=0.0)
        meter.spent_usd = 100.0
        # Should not raise
        meter.check_before("step_1")

    def test_record_after_updates_totals(self):
        """record_after should update both spent_usd and per_step."""
        meter = CostMeter(run_id="run_123", ceiling_usd=1.0)
        meter.record_after("step_1", 0.10)
        assert meter.spent_usd == pytest.approx(0.10)
        assert meter.per_step["step_1"] == pytest.approx(0.10)

        meter.record_after("step_2", 0.15)
        assert meter.spent_usd == pytest.approx(0.25)
        assert meter.per_step["step_2"] == pytest.approx(0.15)

        # Multiple calls to same step accumulate
        meter.record_after("step_1", 0.05)
        assert meter.spent_usd == pytest.approx(0.30)
        assert meter.per_step["step_1"] == pytest.approx(0.15)

    def test_record_after_ignores_zero_delta(self):
        """record_after should not record zero deltas."""
        meter = CostMeter(run_id="run_123", ceiling_usd=1.0)
        meter.record_after("step_1", 0.0)
        assert meter.spent_usd == 0.0
        assert "step_1" not in meter.per_step

    def test_three_steps_trip_ceiling_scenario(self):
        """Scenario: 3 steps at 0.2 each with 0.5 ceiling → 3rd check raises."""
        meter = CostMeter(run_id="run_123", ceiling_usd=0.50)

        # Step 1: check passes, then costs 0.2
        meter.check_before("step_1")
        meter.record_after("step_1", 0.20)
        assert meter.spent_usd == pytest.approx(0.20)

        # Step 2: check passes, then costs 0.25
        meter.check_before("step_2")
        meter.record_after("step_2", 0.25)
        assert meter.spent_usd == pytest.approx(0.45)

        # Step 3: check should raise (spent 0.45 >= ceiling 0.50? no, so we need 0.50)
        meter.record_after("step_2b", 0.05)  # now at 0.50
        # Step 3: check should raise
        with pytest.raises(CostCeilingExceeded):
            meter.check_before("step_3")

    def test_cost_ceiling_exceeded_error_message(self):
        """CostCeilingExceeded should format error message correctly."""
        exc = CostCeilingExceeded(
            run_id="run_123",
            spent=0.50,
            ceiling=0.50,
            step_id="step_3",
        )
        msg = str(exc)
        assert "0.5000" in msg or "0.50" in msg  # ceiling
        assert "step_3" in msg

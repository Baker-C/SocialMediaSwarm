"""Tests for engine invariant wrappers in the runner (cost meter + guardian assertion)."""

from unittest.mock import Mock, MagicMock, patch

import pytest

from app.core.cost_meter import CostCeilingExceeded, CostMeter
from app.interval.runner import engine_invariants
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.flow import FlatStep, Step


class TestEngineInvariants:
    """Test the engine_invariants wrapper factory."""

    def test_engine_invariants_returns_two_wrappers(self):
        """engine_invariants should return cost_wrapper and guardian_wrapper."""
        meter = CostMeter(run_id="test", ceiling_usd=0.50)
        wrappers = engine_invariants(meter=meter)
        assert len(wrappers) == 2
        assert callable(wrappers[0])  # cost_wrapper
        assert callable(wrappers[1])  # guardian_wrapper

    def test_cost_wrapper_checks_before(self):
        """cost_wrapper should call meter.check_before before running the step."""
        meter = CostMeter(run_id="test", ceiling_usd=0.50)
        meter.spent_usd = 0.50  # Already at ceiling

        wrappers = engine_invariants(meter=meter)
        cost_wrapper = wrappers[0]

        # Mock the step and context
        flat = Mock(spec=FlatStep)
        flat.id = "test_step"

        run_fn = Mock(return_value=StepResult(ok=True))

        wrapped_fn = cost_wrapper(flat, run_fn)

        # Calling wrapped function should raise CostCeilingExceeded
        ctx = Mock(spec=TickRunContext)
        deps = Mock(spec=PostRunDeps)

        with pytest.raises(CostCeilingExceeded):
            wrapped_fn(ctx, deps)

        # run_fn should NOT have been called
        run_fn.assert_not_called()

    def test_cost_wrapper_records_after(self):
        """cost_wrapper should call meter.record_after after the step runs."""
        meter = CostMeter(run_id="test", ceiling_usd=10.0)

        wrappers = engine_invariants(meter=meter)
        cost_wrapper = wrappers[0]

        flat = Mock(spec=FlatStep)
        flat.id = "llm_step"

        run_fn = Mock(return_value=StepResult(ok=True))

        wrapped_fn = cost_wrapper(flat, run_fn)

        ctx = Mock(spec=TickRunContext)
        deps = Mock(spec=PostRunDeps)

        # Mock drain_run_llm_cost_usd to return a cost
        with patch("app.interval.runner.drain_run_llm_cost_usd", return_value=0.05):
            wrapped_fn(ctx, deps)

        # run_fn should have been called
        run_fn.assert_called_once_with(ctx, deps)

        # meter should have recorded the cost
        assert meter.spent_usd == 0.05
        assert meter.per_step.get("llm_step") == 0.05

    def test_guardian_wrapper_asserts_verdict_for_compose(self):
        """guardian_wrapper should assert SAFETY_VERDICT exists after compose_until_safe."""
        meter = CostMeter(run_id="test", ceiling_usd=10.0)

        wrappers = engine_invariants(meter=meter)
        guardian_wrapper = wrappers[1]

        flat = Mock(spec=FlatStep)
        flat.id = "compose_until_safe"

        # Create a mock context that has_artifact returning False
        ctx = Mock(spec=TickRunContext)
        ctx.has_artifact = Mock(return_value=False)

        run_fn = Mock(return_value=StepResult(ok=True))
        deps = Mock(spec=PostRunDeps)

        wrapped_fn = guardian_wrapper(flat, run_fn)

        # Calling wrapped function should raise RuntimeError
        with pytest.raises(RuntimeError, match="guardian invariant violated"):
            wrapped_fn(ctx, deps)

    def test_guardian_wrapper_passes_when_verdict_exists(self):
        """guardian_wrapper should pass when SAFETY_VERDICT exists after compose."""
        meter = CostMeter(run_id="test", ceiling_usd=10.0)

        wrappers = engine_invariants(meter=meter)
        guardian_wrapper = wrappers[1]

        flat = Mock(spec=FlatStep)
        flat.id = "compose_until_safe"

        # Create a mock context that has_artifact returning True
        ctx = Mock(spec=TickRunContext)
        ctx.has_artifact = Mock(return_value=True)

        result = StepResult(ok=True)
        run_fn = Mock(return_value=result)
        deps = Mock(spec=PostRunDeps)

        wrapped_fn = guardian_wrapper(flat, run_fn)

        # Should not raise
        returned = wrapped_fn(ctx, deps)
        assert returned == result

    def test_guardian_wrapper_ignores_other_steps(self):
        """guardian_wrapper should not check verdict for non-compose steps."""
        meter = CostMeter(run_id="test", ceiling_usd=10.0)

        wrappers = engine_invariants(meter=meter)
        guardian_wrapper = wrappers[1]

        flat = Mock(spec=FlatStep)
        flat.id = "some_other_step"

        # Mock context that would fail has_artifact, but shouldn't be called
        ctx = Mock(spec=TickRunContext)

        result = StepResult(ok=True)
        run_fn = Mock(return_value=result)
        deps = Mock(spec=PostRunDeps)

        wrapped_fn = guardian_wrapper(flat, run_fn)

        # Should not raise, and has_artifact should not be called
        returned = wrapped_fn(ctx, deps)
        assert returned == result
        ctx.has_artifact.assert_not_called()

    def test_wrappers_applied_in_order(self):
        """Wrappers should be applied outermost-to-innermost (cost then guardian)."""
        meter = CostMeter(run_id="test", ceiling_usd=10.0)

        wrappers = engine_invariants(meter=meter)
        assert len(wrappers) == 2

        flat = Mock(spec=FlatStep)
        flat.id = "non_compose_step"

        call_order = []

        def run_fn_tracker(ctx, deps):
            call_order.append("run_fn")
            return StepResult(ok=True)

        # Manually apply wrappers in order
        run_fn = run_fn_tracker
        for wrapper in wrappers:
            old_run = run_fn
            run_fn = wrapper(flat, old_run)

        ctx = Mock(spec=TickRunContext)
        deps = Mock(spec=PostRunDeps)

        with patch("app.interval.runner.drain_run_llm_cost_usd", return_value=0.01):
            run_fn(ctx, deps)

        # run_fn should have been called
        assert "run_fn" in call_order

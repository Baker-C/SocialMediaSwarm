"""Tests for LLM cost tracking in ClaudeClient."""

import pytest

from app.infrastructure.claude_client import (
    _tokens_to_usd,
    _record_usage,
    drain_run_llm_cost_usd,
)


class MockUsage:
    """Mock SDK usage object."""

    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class TestTokensToUsd:
    """Test the _tokens_to_usd helper."""

    def test_tokens_to_usd_basic(self):
        """_tokens_to_usd should convert tokens to USD correctly."""
        # With default 0.009 USD per 1K tokens:
        # 1000 total tokens = 0.009 USD
        result = _tokens_to_usd(500, 500)
        expected = 1000 / 1000.0 * 0.009
        assert result == pytest.approx(expected, abs=1e-6)

    def test_tokens_to_usd_zero_tokens(self):
        """_tokens_to_usd should handle zero tokens."""
        result = _tokens_to_usd(0, 0)
        assert result == 0.0

    def test_tokens_to_usd_input_only(self):
        """_tokens_to_usd should handle input-only tokens."""
        result = _tokens_to_usd(1000, 0)
        expected = 1000 / 1000.0 * 0.009
        assert result == pytest.approx(expected, abs=1e-6)

    def test_tokens_to_usd_output_only(self):
        """_tokens_to_usd should handle output-only tokens."""
        result = _tokens_to_usd(0, 1000)
        expected = 1000 / 1000.0 * 0.009
        assert result == pytest.approx(expected, abs=1e-6)


class TestRecordUsage:
    """Test the _record_usage and drain functions."""

    def test_record_usage_none_handling(self):
        """_record_usage should handle None gracefully."""
        # Reset the accumulator
        drain_run_llm_cost_usd()
        _record_usage(None)
        assert drain_run_llm_cost_usd() == pytest.approx(0.0)

    def test_record_usage_accumulates(self):
        """_record_usage should accumulate cost across calls."""
        drain_run_llm_cost_usd()  # reset

        # First call
        _record_usage(MockUsage(500, 500))
        # Second call
        _record_usage(MockUsage(300, 200))

        # Drain should return total of both
        total = drain_run_llm_cost_usd()
        expected = (1000 / 1000.0) * 0.009 + (500 / 1000.0) * 0.009
        assert total == pytest.approx(expected, abs=1e-6)

    def test_drain_resets_accumulator(self):
        """drain_run_llm_cost_usd should reset the accumulator."""
        drain_run_llm_cost_usd()  # reset
        _record_usage(MockUsage(1000, 0))
        first_drain = drain_run_llm_cost_usd()
        assert first_drain > 0

        # Second drain should return 0 (reset)
        second_drain = drain_run_llm_cost_usd()
        assert second_drain == 0.0

    def test_accumulator_per_run(self):
        """Each run should have its own accumulator context."""
        drain_run_llm_cost_usd()  # reset
        _record_usage(MockUsage(1000, 0))
        cost1 = drain_run_llm_cost_usd()

        # Start a new "run"
        _record_usage(MockUsage(500, 0))
        cost2 = drain_run_llm_cost_usd()

        # costs should be different
        assert cost1 > 0
        assert cost2 > 0
        assert cost1 != cost2

"""Per-run cost ceiling. Engine-injected, non-bypassable. Synchronous."""

from __future__ import annotations

from dataclasses import dataclass, field


class CostCeilingExceeded(RuntimeError):
    """Raised when a run exceeds its hard cost ceiling before a step executes."""

    def __init__(self, run_id: str, spent: float, ceiling: float, step_id: str) -> None:
        super().__init__(f"cost ceiling {ceiling:.4f} exceeded ({spent:.4f}) before {step_id}")
        self.run_id = run_id
        self.spent = spent
        self.ceiling = ceiling
        self.step_id = step_id


@dataclass
class CostMeter:
    """Hard per-run cost ceiling, checked before each leaf runs.

    Attributes:
        run_id: The run ID for error reporting.
        ceiling_usd: The hard cost ceiling in USD. 0.0 disables enforcement.
        spent_usd: Accumulated LLM cost in USD (updated by record_after).
        per_step: Per-step cost tracking for debugging.
    """

    run_id: str
    ceiling_usd: float
    spent_usd: float = 0.0
    per_step: dict[str, float] = field(default_factory=dict)

    def check_before(self, step_id: str) -> None:
        """Verify the run is within budget before a step executes.

        Raises:
            CostCeilingExceeded: If ceiling_usd > 0 and spent_usd >= ceiling_usd.
        """
        if self.ceiling_usd > 0 and self.spent_usd >= self.ceiling_usd:
            raise CostCeilingExceeded(self.run_id, self.spent_usd, self.ceiling_usd, step_id)

    def record_after(self, step_id: str, delta: float) -> None:
        """Record LLM spend for a completed step.

        Args:
            step_id: The step identifier.
            delta: The USD spend for this step, drained from ClaudeClient's per-run accumulator.
        """
        if delta:
            self.spent_usd += delta
            self.per_step[step_id] = self.per_step.get(step_id, 0.0) + delta

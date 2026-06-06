"""Weighted interaction scoring for reference pools."""

from __future__ import annotations

from typing import Any

from app.interval.tweet_topic_preanalysis import popularity_score
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "deterministic.reference_score"
TOOL_KIND = "deterministic"
TOOL_PURPOSE = "Compute weighted engagement score for a metrics row"


def run(
    ctx: TickRunContext,
    *,
    metrics: dict[str, Any],
) -> StepResult:
    score = score_row(metrics)
    return StepResult(ok=True, payload={"score": score, "metrics": metrics})


def score_row(metrics: dict[str, Any]) -> float:
    return popularity_score(metrics)

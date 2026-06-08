"""Rank reference pools and select top performers."""

from __future__ import annotations

from typing import Any

from app.interval.tweet_topic_preanalysis import (
    GatheredTweet,
    rank_timeline_references,
    select_top_timeline_reference,
)
from app.metrics.derived import normalized_reference_score
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

TOOL_ID = "deterministic.reference_rank"
TOOL_KIND = "deterministic"
TOOL_PURPOSE = "Rank reference tweet rows by interaction score and select top N"


def run(
    ctx: TickRunContext,
    *,
    rows: list[dict[str, Any]],
    top_n: int = 10,
    exclude_ids: frozenset[str] | None = None,
    store_key: str = "ranked_references",
) -> StepResult:
    ranked = rank_rows(rows, top_n=top_n, exclude_ids=exclude_ids)
    payload = {
        "ranked": [t.model_dump() for t in ranked],
        "winner": ranked[0].model_dump() if ranked else None,
    }
    ctx.set(store_key, payload)
    return StepResult(ok=True, payload=payload)


def rank_rows(
    rows: list[dict[str, Any]],
    *,
    top_n: int = 10,
    exclude_ids: frozenset[str] | None = None,
) -> list[GatheredTweet]:
    ranked = rank_timeline_references(rows, exclude_ids=exclude_ids)
    if ranked:
        ranked = sorted(
            ranked,
            key=lambda t: normalized_reference_score(t.metrics, _to_int(t.metrics.get("author_followers_count"))),
            reverse=True,
        )
    if top_n > 0:
        ranked = ranked[:top_n]
    return ranked


def pick_winner(
    rows: list[dict[str, Any]],
    *,
    exclude_ids: frozenset[str] | None = None,
) -> GatheredTweet | None:
    return select_top_timeline_reference(rows, exclude_ids=exclude_ids)


def _to_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None

"""merge_reference_pool_rows and merge_reference_pools step tests."""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.types.context import TickRunContext
from app.services.tick_data_service import TickDataService


def test_merge_reference_pool_rows_dedupes_by_id() -> None:
    a = [{"id": "1", "text": "timeline"}, {"id": "2", "text": "timeline2"}]
    b = [{"tweet_id": "2", "text": "search dup"}, {"id": "3", "text": "search only"}]
    merged = TickDataService.merge_reference_pool_rows(a, b)
    assert [r.get("id") or r.get("tweet_id") for r in merged] == ["1", "2", "3"]
    assert merged[1]["text"] == "timeline2"


def test_merge_reference_pools_step_updates_timeline_payload() -> None:
    ctx = TickRunContext(account_id="a1", slot="s1")
    ctx.set(
        "timeline_references",
        {
            "timeline_reference_tweets": [{"id": "t1", "text": "tl"}],
            "reference_errors": [],
        },
    )
    ctx.set(
        "search_references",
        {
            "search_reference_tweets": [{"id": "s1", "text": "search"}],
            "search_queries": ["news"],
            "reference_errors": ["search:q:402"],
        },
    )

    result = steps.merge_reference_pools(ctx, None)  # type: ignore[arg-type]

    assert result.ok
    payload = ctx.get("timeline_references")
    assert payload["search_merged_count"] == 1
    assert payload["timeline_only_count"] == 1
    assert payload["search_queries_run"] == ["news"]
    assert len(payload["timeline_reference_tweets"]) == 2
    assert "search:q:402" in payload["reference_errors"]

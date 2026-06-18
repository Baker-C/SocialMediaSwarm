"""Reference pool helper tests (the following-timeline pull was removed)."""

from app.services.tick_data_service import TickDataService


def test_merge_reference_pool_dedupes_timeline() -> None:
    payload = {
        "timeline_reference_tweets": [
            {"id": "1", "text": "a"},
            {"id": "1", "text": "dup"},
            {"tweet_id": "2", "text": "b"},
        ],
    }
    pool = TickDataService.merge_reference_pool(payload)
    assert len(pool) == 2
    ids = {r.get("id") or r.get("tweet_id") for r in pool}
    assert ids == {"1", "2"}

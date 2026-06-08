"""TickDataService.compile_search_reference_tweets tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.tick_data_service import TickDataService


def test_compile_search_reference_tweets_merges_queries_and_dedupes() -> None:
    twitter = MagicMock()
    twitter.search_tweets.side_effect = [
        [
            {"id": "1", "text": "first", "like_count": 10},
            {"id": "2", "text": "second", "like_count": 5},
        ],
        [
            {"id": "2", "text": "second again", "like_count": 6},
            {"id": "3", "text": "third", "like_count": 1},
        ],
    ]
    pulled = MagicMock()
    pulled.record_pulls.return_value = MagicMock(
        model_dump=lambda: {"new_count": 3, "duplicate_count": 0, "skipped_no_id": 0}
    )
    svc = TickDataService(MagicMock(), twitter, pulled_tweets=pulled)

    payload = svc.compile_search_reference_tweets(
        "acct",
        queries=["q1", "q2", "q1"],
        slot="2026-06-08-10",
        authenticated_user_id="99",
    )

    assert payload["search_queries"] == ["q1", "q2"]
    assert payload["per_query_counts"] == {"q1": 2, "q2": 2}
    ids = {r["id"] for r in payload["search_reference_tweets"]}
    assert ids == {"1", "2", "3"}
    row2 = next(r for r in payload["search_reference_tweets"] if r["id"] == "2")
    assert row2["source"] == "search_recent"
    assert row2["search_query"] == "q1"
    assert row2["matched_queries"] == ["q1", "q2"]
    twitter.search_tweets.assert_any_call("acct", "q1", max_results=None)
    twitter.search_tweets.assert_any_call("acct", "q2", max_results=None)


def test_compile_search_reference_tweets_continues_after_query_error() -> None:
    twitter = MagicMock()
    twitter.search_tweets.side_effect = [
        RuntimeError("402 Payment Required"),
        [{"id": "9", "text": "ok"}],
    ]
    svc = TickDataService(MagicMock(), twitter)

    payload = svc.compile_search_reference_tweets(
        "acct",
        queries=["bad", "good"],
        slot="slot",
    )

    assert len(payload["search_reference_tweets"]) == 1
    assert payload["search_reference_tweets"][0]["id"] == "9"
    assert any("search:bad:" in e for e in payload["reference_errors"])


def test_compile_search_reference_tweets_filters_own_tweets() -> None:
    twitter = MagicMock()
    twitter.search_tweets.return_value = [
        {"id": "1", "text": "mine", "author_id": "99"},
        {"id": "2", "text": "theirs", "author_id": "42"},
    ]
    svc = TickDataService(MagicMock(), twitter)

    payload = svc.compile_search_reference_tweets(
        "acct",
        queries=["news"],
        slot="slot",
        authenticated_user_id="99",
    )

    assert [r["id"] for r in payload["search_reference_tweets"]] == ["2"]

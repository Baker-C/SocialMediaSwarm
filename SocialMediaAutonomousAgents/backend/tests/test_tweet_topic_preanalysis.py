"""Timeline reference selection tests."""

from app.interval.tweet_topic_preanalysis import (
    popularity_score,
    run_reference_preanalysis,
    select_top_timeline_reference,
)


def test_popularity_score_weighted_includes_quotes() -> None:
    row = {
        "like_count": 10,
        "reply_count": 2,
        "retweet_count": 3,
        "quote_count": 100,
        "impression_count": 0,
    }
    assert popularity_score(row) == 91.2


def test_popularity_score_includes_impressions() -> None:
    row = {
        "like_count": 0,
        "reply_count": 0,
        "retweet_count": 0,
        "impression_count": 1000,
    }
    assert popularity_score(row) == 100.0


def test_select_top_timeline_reference_picks_highest_popularity() -> None:
    rows = [
        {"id": "1", "text": "low https://example.com/a", "like_count": 1},
        {"id": "2", "text": "high https://example.com/b", "like_count": 50, "reply_count": 2},
    ]
    pick = select_top_timeline_reference(rows)
    assert pick is not None
    assert pick.tweet_id == "2"
    assert pick.popularity_score == 36.2


def test_select_top_timeline_reference_falls_back_when_top_copied() -> None:
    rows = [
        {"id": "1", "text": "top https://example.com/a", "like_count": 100},
        {"id": "2", "text": "next https://example.com/b", "like_count": 40},
    ]
    pick = select_top_timeline_reference(rows, exclude_ids=frozenset({"1"}))
    assert pick is not None
    assert pick.tweet_id == "2"


def test_run_reference_preanalysis_skipped_when_empty() -> None:
    result = run_reference_preanalysis([], niche="Tech")
    assert result.skipped is True
    assert result.skip_reason == "no_reference_with_urls"


def test_run_reference_preanalysis_selects_winner_and_embed() -> None:
    rows = [
        {
            "id": "99",
            "text": "Story with link https://example.com/x",
            "like_count": 10,
            "tweet_permalink": "https://x.com/i/status/99",
        },
    ]
    result = run_reference_preanalysis(rows, niche="News")
    assert result.skipped is False
    assert result.selected_tweet_ids == ["99"]
    assert result.chosen_embed_url == "https://example.com/x"
    assert len(result.filtered_post_engagements) == 1

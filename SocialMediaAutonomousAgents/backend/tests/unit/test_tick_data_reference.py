"""Timeline reference tweet compile tests."""

from unittest.mock import MagicMock, patch

from app.services.tick_data_service import TickDataService


@patch("app.services.tick_data_service.settings")
def test_compile_timeline_reference_fetches_following(mock_settings) -> None:
    mock_settings.following_feed_enabled = True
    mock_settings.following_timeline_max_results = 100
    mock_settings.reference_tweet_cache_minutes = 45

    twitter = MagicMock()
    twitter.get_following_feed.return_value = [
        {"id": "1", "text": "a https://t.co/x", "like_count": 1},
    ]
    repo = MagicMock()
    pulled = MagicMock()
    pulled.record_pulls.return_value = MagicMock(
        model_dump=lambda: {"new_count": 1, "duplicate_count": 0, "skipped_no_id": 0}
    )

    svc = TickDataService(repo, twitter, pulled_tweets=pulled)
    payload = svc.compile_timeline_reference_tweets(
        "acct",
        authenticated_user_id="me",
        slot="2026-05-18-10",
    )

    assert len(payload["timeline_reference_tweets"]) == 1
    assert payload["timeline_reference_tweets"][0]["id"] == "1"
    twitter.get_following_feed.assert_called_once()
    pulled.record_pulls.assert_called_once()


@patch("app.services.tick_data_service.settings")
def test_compile_timeline_reference_cache_hit_still_records_pulls(mock_settings) -> None:
    from app.services import reference_tweet_cache

    reference_tweet_cache.clear_cache()
    mock_settings.following_feed_enabled = True
    mock_settings.following_timeline_max_results = 100
    mock_settings.reference_tweet_cache_minutes = 45

    twitter = MagicMock()
    twitter.get_following_feed.return_value = [{"id": "9", "text": "cached https://x.com"}]
    pulled = MagicMock()
    pulled.record_pulls.return_value = MagicMock(
        model_dump=lambda: {"new_count": 0, "duplicate_count": 1, "skipped_no_id": 0}
    )
    svc = TickDataService(MagicMock(), twitter, pulled_tweets=pulled)

    svc.compile_timeline_reference_tweets("acct", authenticated_user_id=None, slot="s1")
    twitter.get_following_feed.reset_mock()
    payload = svc.compile_timeline_reference_tweets("acct", authenticated_user_id=None, slot="s1")

    twitter.get_following_feed.assert_not_called()
    assert len(payload["timeline_reference_tweets"]) == 1
    pulled.record_pulls.assert_called()


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

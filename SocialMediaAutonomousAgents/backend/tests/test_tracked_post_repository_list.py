"""TrackedPostRepository list_for_account filters and get_for_tweet."""

from unittest.mock import MagicMock

from app.services.post_registry import TrackedPostRepository


def test_list_for_account_applies_since_and_limit() -> None:
    client = MagicMock()
    client.query.return_value = [
        {"account_id": "a", "tweet_id": "1", "posted_at": "2026-06-01T00:00:00+00:00"},
        {"account_id": "a", "tweet_id": "2", "posted_at": "2026-06-08T00:00:00+00:00"},
        {"account_id": "a", "tweet_id": "3", "posted_at": "2026-06-09T00:00:00+00:00"},
    ]
    repo = TrackedPostRepository(client=client)

    rows = repo.list_for_account("a", since="2026-06-07T00:00:00+00:00", limit=1)

    assert len(rows) == 1
    assert rows[0]["tweet_id"] == "3"


def test_get_for_tweet_returns_document() -> None:
    client = MagicMock()
    client.get_document.return_value = {
        "account_id": "a",
        "tweet_id": "99",
        "posted_at": "t0",
    }
    repo = TrackedPostRepository(client=client)

    row = repo.get_for_tweet("a", "99")

    assert row is not None
    assert row["tweet_id"] == "99"
    client.get_document.assert_called_once_with("trackedposts/a-99")


def test_get_for_tweet_returns_none_when_missing() -> None:
    client = MagicMock()
    client.get_document.return_value = None
    repo = TrackedPostRepository(client=client)
    assert repo.get_for_tweet("a", "missing") is None

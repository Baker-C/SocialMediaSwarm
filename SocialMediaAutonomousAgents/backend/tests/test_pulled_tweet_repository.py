"""PulledTweets repository upsert and list-by-account."""

from unittest.mock import MagicMock

from app.models.pulled_tweet import PulledTweetDocument
from app.services.pulled_tweet_repository import PulledTweetRepository


def _row(tweet_id: str, *, source: str = "search_recent", account: str = "a1") -> dict:
    return {
        "id": tweet_id,
        "text": f"text {tweet_id}",
        "author_id": "99",
        "source": source,
        "like_count": 10,
    }


def test_record_pulls_inserts_new_document() -> None:
    client = MagicMock()
    client.get_document.return_value = None
    repo = PulledTweetRepository(client=client)

    stats = repo.record_pulls([_row("111")], account_id="acct_a", slot="2026-05-15-10")

    assert stats.new_count == 1
    assert stats.duplicate_count == 0
    assert stats.skipped_no_id == 0
    client.put_document.assert_called_once()
    doc_id, payload, kwargs = (
        client.put_document.call_args[0][0],
        client.put_document.call_args[0][1],
        client.put_document.call_args.kwargs,
    )
    assert doc_id == "pulledtweets/111"
    assert kwargs.get("collection") == "PulledTweets"
    assert payload["duplicate_fetch_count"] == 0
    assert payload["pull_count"] == 1
    assert payload["first_pulled_for_account_id"] == "acct_a"
    assert payload["pulled_for_account_ids"] == ["acct_a"]


def test_record_pulls_increments_duplicate_fetch_count() -> None:
    client = MagicMock()
    existing = PulledTweetDocument(
        tweet_id="222",
        text="old",
        duplicate_fetch_count=0,
        pull_count=1,
        first_pulled_at="2026-05-14T00:00:00+00:00",
        last_pulled_at="2026-05-14T00:00:00+00:00",
        first_pulled_for_account_id="acct_a",
        last_pulled_for_account_id="acct_a",
        pulled_for_account_ids=["acct_a"],
    )
    client.get_document.return_value = existing.model_dump()
    repo = PulledTweetRepository(client=client)

    stats = repo.record_pulls([_row("222")], account_id="acct_a", slot="2026-05-15-11")

    assert stats.new_count == 0
    assert stats.duplicate_count == 1
    payload = client.put_document.call_args[0][1]
    assert payload["duplicate_fetch_count"] == 1
    assert payload["pull_count"] == 2
    assert payload["last_pulled_for_account_id"] == "acct_a"


def test_record_pulls_appends_second_account() -> None:
    client = MagicMock()
    existing = PulledTweetDocument(
        tweet_id="333",
        first_pulled_at="t0",
        last_pulled_at="t0",
        first_pulled_for_account_id="acct_a",
        last_pulled_for_account_id="acct_a",
        pulled_for_account_ids=["acct_a"],
    )
    client.get_document.return_value = existing.model_dump()
    repo = PulledTweetRepository(client=client)

    repo.record_pulls([_row("333")], account_id="acct_b", slot="slot1")

    payload = client.put_document.call_args[0][1]
    assert payload["pulled_for_account_ids"] == ["acct_a", "acct_b"]
    assert payload["last_pulled_for_account_id"] == "acct_b"


def test_record_pulls_stores_media_enrichment() -> None:
    client = MagicMock()
    client.get_document.return_value = None
    repo = PulledTweetRepository(client=client)
    row = {
        "id": "555",
        "text": "clip",
        "source": "search_recent",
        "tweet_permalink": "https://x.com/i/status/555",
        "media_types": ["video"],
        "primary_media_type": "video",
        "media": [{"media_key": "m1", "type": "video", "url": "https://video.twimg.com/x.mp4"}],
        "embed_urls": ["https://x.com/i/status/555", "https://example.com/article"],
        "url_entities": [{"expanded_url": "https://example.com/article"}],
    }
    repo.record_pulls([row], account_id="acct_a", slot="s1")
    payload = client.put_document.call_args[0][1]
    assert payload["primary_media_type"] == "video"
    assert payload["embed_urls"] == [
        "https://x.com/i/status/555",
        "https://example.com/article",
    ]


def test_record_pulls_skips_missing_id() -> None:
    client = MagicMock()
    repo = PulledTweetRepository(client=client)
    stats = repo.record_pulls([{"text": "no id"}], account_id="a", slot="s")
    assert stats.skipped_no_id == 1
    assert stats.new_count == 0
    client.put_document.assert_not_called()


def test_list_for_account_queries_rql() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "tweet_id": "444",
            "text": "hi",
            "pulled_for_account_ids": ["acct_x"],
            "last_pulled_at": "2026-05-15T12:00:00+00:00",
            "first_pulled_at": "2026-05-15T10:00:00+00:00",
            "first_pulled_for_account_id": "acct_x",
            "last_pulled_for_account_id": "acct_x",
        }
    ]
    repo = PulledTweetRepository(client=client)
    rows = repo.list_for_account("acct_x", limit=50)
    assert len(rows) == 1
    assert rows[0].tweet_id == "444"
    rql = client.query.call_args[0][0]
    assert "acct_x" in rql
    assert "PulledTweets" in rql

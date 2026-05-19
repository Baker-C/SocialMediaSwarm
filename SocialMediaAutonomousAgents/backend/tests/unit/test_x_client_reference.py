from unittest.mock import MagicMock, patch

from app.social.credentials import XOAuth1Credentials
from app.social.implementations.x_client import XTwitterClient
from app.social.reference_rows import filter_out_own_tweets


def _oauth1_client() -> XTwitterClient:
    return XTwitterClient(
        XOAuth1Credentials(
            consumer_key="k",
            consumer_secret="s",
            access_token="t",
            access_token_secret="ts",
        )
    )


def test_filter_out_own_tweets():
    rows = [
        {"id": "1", "author_id": "111", "text": "mine"},
        {"id": "2", "author_id": "222", "text": "theirs"},
    ]
    out = filter_out_own_tweets(rows, "111")
    assert len(out) == 1
    assert out[0]["id"] == "2"


@patch("tweepy.Client.search_recent_tweets")
def test_search_recent_maps_rows(mock_search):
    tweet = MagicMock()
    tweet.id = "999"
    tweet.text = "Hello from search"
    tweet.author_id = "42"
    tweet.public_metrics = {"like_count": 10}
    tweet.created_at = None
    tweet.lang = "en"
    tweet.data = None
    resp = MagicMock()
    resp.data = [tweet]
    mock_search.return_value = resp

    client = _oauth1_client()
    rows = client.search_recent_tweets("#test -is:retweet lang:en", max_results=10, trend_query="test")
    assert len(rows) == 1
    assert rows[0]["id"] == "999"
    assert rows[0]["source"] == "search_recent"
    assert rows[0]["text"] == "Hello from search"

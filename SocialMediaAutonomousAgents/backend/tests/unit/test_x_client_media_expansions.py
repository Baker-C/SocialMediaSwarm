"""X client passes media expansions on reference fetches."""

from unittest.mock import MagicMock, patch

from app.social.credentials import XOAuth2UserCredentials
from app.social.implementations.x_client import XTwitterClient


def test_search_recent_tweets_requests_media_expansions() -> None:
    creds = XOAuth2UserCredentials(access_token="tok")

    class _Tweet:
        id = "1"
        text = "hello world"

    mock_resp = MagicMock()
    mock_resp.data = [_Tweet()]
    mock_resp.includes = {}

    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.search_recent_tweets.return_value = mock_resp
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        rows = x.search_recent_tweets("test query", max_results=10)

    assert len(rows) == 1
    call_kw = mock_client.search_recent_tweets.call_args.kwargs
    assert "attachments" in call_kw["tweet_fields"]
    assert call_kw["expansions"] == ["attachments.media_keys"]
    assert "type" in call_kw["media_fields"]

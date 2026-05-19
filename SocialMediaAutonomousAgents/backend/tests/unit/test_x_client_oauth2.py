"""XTwitterClient OAuth2 path: Bearer user token and v2 trends request."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.social.credentials import XOAuth2UserCredentials
from app.social.implementations.x_client import XTwitterClient


def test_oauth2_create_post_uses_user_auth_false():
    creds = XOAuth2UserCredentials(access_token="tok")

    class _Tweet:
        id = "42"

    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data=_Tweet())
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        out = x.create_post("hello world")
    assert out.id == "42"
    mock_client.create_tweet.assert_called_once_with(text="hello world", user_auth=False)


def test_oauth2_get_trends_parses_v2_payload():
    creds = XOAuth2UserCredentials(access_token="tok")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"trend_name": "#One", "tweet_count": 100},
            {"name": "Two", "tweet_volume": 50},
        ],
        "meta": {"location_name": "Worldwide"},
    }
    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.request.return_value = mock_resp
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        tr = x.get_trends(woeid=1, limit=10, prefer_personalized=False)
    mock_client.request.assert_called_once_with("GET", "/2/trends/by/woeid/1", user_auth=False)
    assert len(tr.trends) == 2
    assert tr.trends[0].name == "#One"
    assert tr.trends[0].tweet_volume == 100
    assert tr.trends[1].name == "Two"
    assert tr.location_name == "Worldwide"


def test_oauth2_get_trends_non_200_returns_empty():
    creds = XOAuth2UserCredentials(access_token="tok")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "forbidden"
    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.request.return_value = mock_resp
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        tr = x.get_trends(woeid=1, prefer_personalized=False)
    assert tr.trends == []
    assert tr.woeid == 1


def test_oauth2_prefers_personalized_trends_before_woeid():
    creds = XOAuth2UserCredentials(access_token="tok")
    personalized_resp = MagicMock()
    personalized_resp.status_code = 200
    personalized_resp.json.return_value = {
        "data": [{"trend_name": "#ForYou", "tweet_count": 500}],
        "meta": {"location_name": "Personalized"},
    }
    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.request.return_value = personalized_resp
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        tr = x.get_trends(woeid=1, limit=10, prefer_personalized=True)
    mock_client.request.assert_called_once_with(
        "GET", "/2/users/personalized_trends", user_auth=False
    )
    assert tr.source == "personalized"
    assert tr.trends[0].name == "#ForYou"


def test_oauth2_falls_back_to_woeid_when_personalized_empty():
    creds = XOAuth2UserCredentials(access_token="tok")
    empty_personal = MagicMock()
    empty_personal.status_code = 403
    empty_personal.text = "forbidden"
    woeid_resp = MagicMock()
    woeid_resp.status_code = 200
    woeid_resp.json.return_value = {
        "data": [{"name": "FallbackTrend", "tweet_volume": 10}],
    }

    def _request(method, path, **kwargs):
        if path == "/2/users/personalized_trends":
            return empty_personal
        return woeid_resp

    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_client = MagicMock()
        mock_client.request.side_effect = _request
        ClientCls.return_value = mock_client
        x = XTwitterClient(creds)
        tr = x.get_trends(woeid=1, limit=10, prefer_personalized=True)
    assert tr.source == "woeid"
    assert tr.trends[0].name == "FallbackTrend"

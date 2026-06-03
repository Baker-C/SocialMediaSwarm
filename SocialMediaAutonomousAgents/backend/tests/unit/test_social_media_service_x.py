"""SocialMediaService facade tests for X platform routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.social.credentials import XOAuth2UserCredentials
from app.social.dtos import AccountData, CreatedPost, PostData, TrendsResult, TrendItem
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from app.social.service import SocialMediaService


def _creds() -> XOAuth2UserCredentials:
    return XOAuth2UserCredentials(access_token="tok")


@pytest.fixture
def svc() -> SocialMediaService:
    return SocialMediaService()


def test_missing_credentials_raises(svc: SocialMediaService) -> None:
    with pytest.raises(SocialPlatformError, match="credentials are required"):
        svc.get_trends(SocialPlatform.X, None)


def test_unsupported_platform_raises(svc: SocialMediaService) -> None:
    class _FakePlatform:
        value = "instagram"

    with pytest.raises(SocialPlatformError, match="Unsupported platform"):
        svc._client(_FakePlatform(), _creds())  # type: ignore[arg-type]


@patch("app.social.service.XTwitterClient")
def test_get_trends_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.get_trends.return_value = TrendsResult(
        trends=[TrendItem(name="#A")],
        source="woeid",
    )
    mock_client_cls.return_value = mock_client
    creds = _creds()

    out = svc.get_trends(SocialPlatform.X, creds, woeid=2, limit=5, prefer_personalized=False)
    mock_client.get_trends.assert_called_once_with(woeid=2, limit=5, prefer_personalized=False)
    assert out.trends[0].name == "#A"


@patch("app.social.service.XTwitterClient")
def test_get_account_data_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.get_account_data.return_value = AccountData(id="1", username="u")
    mock_client_cls.return_value = mock_client

    out = svc.get_account_data(SocialPlatform.X, _creds(), username="u")
    mock_client.get_account_data.assert_called_once_with(user_id=None, username="u")
    assert out.username == "u"


@patch("app.social.service.XTwitterClient")
def test_get_post_data_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.get_post_data.return_value = PostData(id="99", text="t")
    mock_client_cls.return_value = mock_client

    out = svc.get_post_data(SocialPlatform.X, _creds(), "99")
    mock_client.get_post_data.assert_called_once_with("99")
    assert out.id == "99"


@patch("app.social.service.XTwitterClient")
def test_create_post_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.create_post.return_value = CreatedPost(id="1", text="hi")
    mock_client_cls.return_value = mock_client

    out = svc.create_post(SocialPlatform.X, _creds(), "hi")
    mock_client.create_post.assert_called_once_with("hi")
    assert out.id == "1"


@patch("app.social.service.XTwitterClient")
def test_search_recent_tweets_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.search_recent_tweets.return_value = [{"id": "1"}]
    mock_client_cls.return_value = mock_client

    rows = svc.search_recent_tweets(
        SocialPlatform.X,
        _creds(),
        "query",
        max_results=20,
        trend_query="trend",
    )
    mock_client.search_recent_tweets.assert_called_once_with(
        "query",
        max_results=20,
        sort_order="relevancy",
        trend_query="trend",
    )
    assert rows[0]["id"] == "1"


@patch("app.social.service.XTwitterClient")
def test_get_following_timeline_delegates(mock_client_cls: MagicMock, svc: SocialMediaService) -> None:
    mock_client = MagicMock()
    mock_client.get_following_timeline_tweets.return_value = [{"id": "tl"}]
    mock_client_cls.return_value = mock_client

    rows = svc.get_following_timeline_tweets(
        SocialPlatform.X,
        _creds(),
        max_results=50,
        exclude_retweets=False,
    )
    mock_client.get_following_timeline_tweets.assert_called_once_with(
        max_results=50,
        exclude_retweets=False,
    )
    assert rows[0]["id"] == "tl"

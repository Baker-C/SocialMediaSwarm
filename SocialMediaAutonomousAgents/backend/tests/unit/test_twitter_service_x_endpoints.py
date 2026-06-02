"""TwitterService tests for all X read/write endpoints (mocked social layer)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.account import AccountDocument
from app.services.twitter_service import TwitterService
from app.social.credentials import XOAuth2UserCredentials
from app.social.dtos import AccountData, CreatedPost, PostData, TrendsResult, TrendItem
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from tests.unit.test_twitter_service_x import FakeRepo


def _tw(acc: AccountDocument | None = None) -> TwitterService:
    return TwitterService(repo=FakeRepo(acc or AccountDocument(account_id="a1", niche="n")))


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_get_following_feed_delegates(mock_creds: MagicMock) -> None:
    tw = _tw()
    with patch.object(
        tw._social,
        "get_following_timeline_tweets",
        return_value=[{"id": "1"}],
    ) as gft:
        rows = tw.get_following_feed("a1", max_results=25)
    gft.assert_called_once_with(SocialPlatform.X, mock_creds.return_value, max_results=25)
    assert rows == [{"id": "1"}]


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_search_tweets_for_trend_builds_query(mock_creds: MagicMock) -> None:
    tw = _tw()
    with patch.object(
        tw._social,
        "search_recent_tweets",
        return_value=[{"id": "s"}],
    ) as srt:
        rows = tw.search_tweets_for_trend("a1", "AI News", max_results=15)
    assert rows == [{"id": "s"}]
    call = srt.call_args
    assert call.kwargs["trend_query"] == "AI News"
    assert call.kwargs["max_results"] == 15
    assert call.args[2] == '"AI News" -is:retweet lang:en'


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_search_tweets_for_trend_empty_name_returns_empty(mock_creds: MagicMock) -> None:
    tw = _tw()
    with patch.object(tw._social, "search_recent_tweets") as srt:
        assert tw.search_tweets_for_trend("a1", "   ") == []
    srt.assert_not_called()


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_get_trends_returns_model_dump(mock_creds: MagicMock) -> None:
    tw = _tw()
    tr = TrendsResult(trends=[TrendItem(name="#X")], source="woeid", woeid=1)
    with patch.object(tw._social, "get_trends", return_value=tr) as gt:
        out = tw.get_trends("a1", woeid=1, limit=10, prefer_personalized=False)
    gt.assert_called_once()
    assert out["trends"][0]["name"] == "#X"


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_get_tweet_metrics_delegates(mock_creds: MagicMock) -> None:
    tw = _tw()
    post = PostData(id="55", text="t", like_count=3)
    with patch.object(tw._social, "get_post_data", return_value=post) as gpd:
        out = tw.get_tweet_metrics("a1", "55")
    gpd.assert_called_once_with(SocialPlatform.X, mock_creds.return_value, "55")
    assert out["id"] == "55"
    assert out["like_count"] == 3


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_get_account_data_uses_handle_when_no_username(mock_creds: MagicMock) -> None:
    acc = AccountDocument(account_id="a1", niche="n", twitter_handle="@myhandle")
    tw = TwitterService(repo=FakeRepo(acc))
    data = AccountData(id="1", username="myhandle")
    with patch.object(tw._social, "get_account_data", return_value=data) as gad:
        out = tw.get_account_data("a1")
    gad.assert_called_once_with(SocialPlatform.X, mock_creds.return_value, username="myhandle")
    assert out["username"] == "myhandle"


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_verify_api_health_success(mock_creds: MagicMock) -> None:
    tw = _tw()
    with patch.object(tw._social, "get_account_data", return_value=AccountData(id="1", username="u")):
        assert tw.verify_api_health("a1") == []


@patch.object(TwitterService, "_x_credentials", return_value=XOAuth2UserCredentials(access_token="tok"))
def test_verify_api_health_failure(mock_creds: MagicMock) -> None:
    tw = _tw()
    err = SocialPlatformError("unauthorized", vendor="x", cause=RuntimeError("401"))
    with patch.object(tw._social, "get_account_data", side_effect=err):
        failures = tw.verify_api_health("a1")
    assert len(failures) == 1
    assert "X API" in failures[0]


@patch.object(TwitterService, "_x_credentials", return_value=None)
def test_get_following_feed_requires_credentials(mock_creds: MagicMock) -> None:
    tw = _tw()
    with pytest.raises(ValueError, match="Missing or invalid X credentials"):
        tw.get_following_feed("a1")


@patch.object(TwitterService, "_x_credentials", return_value=None)
def test_unknown_account_raises(mock_creds: MagicMock) -> None:
    tw = TwitterService(repo=FakeRepo(None))
    with pytest.raises(ValueError, match="Unknown account_id"):
        tw.get_trends("missing")


@patch.object(TwitterService, "_x_credentials")
def test_oauth2_precedence_over_oauth1(mock_xcreds: MagicMock) -> None:
    acc = AccountDocument(account_id="a1", niche="n")
    tw = _tw(acc)
    o2 = XOAuth2UserCredentials(access_token="bearer")
    mock_xcreds.return_value = o2
    with patch.object(tw._social, "create_post", return_value=CreatedPost(id="1", text="x")) as cp:
        tw.post_tweet("a1", "x")
    cp.assert_called_once_with(SocialPlatform.X, o2, "x")

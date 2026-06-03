"""Comprehensive mocked tests for all XTwitterClient API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import tweepy

from app.social.credentials import XOAuth2UserCredentials
from app.social.exceptions import SocialPlatformError
from app.social.implementations.x_client import XTwitterClient


def _oauth2_creds() -> XOAuth2UserCredentials:
    return XOAuth2UserCredentials(access_token="bearer-tok")


def _tweet(
    *,
    tweet_id: str = "100",
    text: str = "Hello world https://t.co/abc",
    author_id: str = "42",
    like_count: int = 5,
) -> MagicMock:
    t = MagicMock()
    t.id = tweet_id
    t.text = text
    t.author_id = author_id
    t.public_metrics = {
        "like_count": like_count,
        "reply_count": 1,
        "retweet_count": 0,
        "quote_count": 0,
        "impression_count": 10,
    }
    t.created_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    t.lang = "en"
    t.data = None
    t.attachments = None
    t.entities = None
    return t


def _tweet_response(*tweets: MagicMock) -> MagicMock:
    resp = MagicMock()
    resp.data = list(tweets) if tweets else []
    resp.includes = {}
    return resp


def _single_tweet_response(tweet: MagicMock) -> MagicMock:
    resp = MagicMock()
    resp.data = tweet
    resp.includes = {}
    return resp


def _tweepy_error(exc_cls: type, message: str, *, status_code: int = 400) -> Exception:
    response = MagicMock()
    response.status_code = status_code
    response.status = status_code
    response.text = message
    response.reason = message
    return exc_cls(response)


def _oauth1_client() -> XTwitterClient:
    with patch("app.social.implementations.x_client.tweepy.Client"):
        return XTwitterClient(_oauth2_creds())


def _oauth2_client() -> XTwitterClient:
    with patch("app.social.implementations.x_client.tweepy.Client"):
        return XTwitterClient(_oauth2_creds())


# --- create_post ---


def test_oauth2_create_post_uses_user_auth_false() -> None:
    creds = _oauth2_creds()

    class _Created:
        id = "77"

    with patch("app.social.implementations.x_client.tweepy.Client") as ClientCls:
        mock_v2 = MagicMock()
        mock_v2.create_tweet.return_value = MagicMock(data=_Created())
        ClientCls.return_value = mock_v2
        client = XTwitterClient(creds)
        out = client.create_post("posted text")

    assert out.id == "77"
    assert out.text == "posted text"
    mock_v2.create_tweet.assert_called_once_with(text="posted text", user_auth=False)


def test_create_post_empty_response_raises() -> None:
    client = _oauth1_client()
    client._v2.create_tweet.return_value = MagicMock(data=None)
    with pytest.raises(SocialPlatformError, match="Empty response"):
        client.create_post("x")


def test_create_post_missing_id_raises() -> None:
    client = _oauth1_client()
    client._v2.create_tweet.return_value = MagicMock(data=MagicMock(id=""))
    with pytest.raises(SocialPlatformError, match="Missing tweet id"):
        client.create_post("x")


def test_create_post_wraps_tweepy_exception() -> None:
    client = _oauth1_client()
    client._v2.create_tweet.side_effect = _tweepy_error(tweepy.TooManyRequests, "rate limit", status_code=429)
    with pytest.raises(SocialPlatformError) as exc_info:
        client.create_post("x")
    assert exc_info.value.vendor == "x"
    assert isinstance(exc_info.value.cause, tweepy.TweepyException)


# --- get_account_data ---


def test_get_account_data_get_me() -> None:
    client = _oauth1_client()
    user = MagicMock()
    user.id = 999
    user.username = "handle"
    user.name = "Display"
    user.description = "bio"
    user.public_metrics = {
        "followers_count": 100,
        "following_count": 50,
        "tweet_count": 200,
        "listed_count": 3,
    }
    user.created_at = "2020-01-01T00:00:00Z"
    user.profile_image_url = "https://pbs.twimg.com/pic.jpg"
    user.verified = True
    user.data = None
    client._v2.get_me.return_value = MagicMock(data=user)

    data = client.get_account_data()
    client._v2.get_me.assert_called_once()
    assert data.id == "999"
    assert data.username == "handle"
    assert data.followers_count == 100
    assert data.verified is True


def test_get_account_data_by_user_id() -> None:
    client = _oauth1_client()
    user = MagicMock()
    user.id = 1
    user.username = "u"
    user.name = None
    user.description = None
    user.profile_image_url = None
    user.verified = None
    user.created_at = None
    user.public_metrics = {}
    user.data = None
    client._v2.get_user.return_value = MagicMock(data=user)

    data = client.get_account_data(user_id="1")
    client._v2.get_user.assert_called_once()
    assert client._v2.get_user.call_args.kwargs["id"] == "1"
    assert data.id == "1"


def test_get_account_data_by_username_strips_at() -> None:
    client = _oauth1_client()
    user = MagicMock()
    user.id = 2
    user.username = "clean"
    user.name = None
    user.description = None
    user.profile_image_url = None
    user.verified = None
    user.created_at = None
    user.public_metrics = {}
    user.data = None
    client._v2.get_user.return_value = MagicMock(data=user)

    data = client.get_account_data(username="@clean")
    assert client._v2.get_user.call_args.kwargs["username"] == "clean"
    assert data.username == "clean"


def test_get_account_data_empty_raises() -> None:
    client = _oauth1_client()
    client._v2.get_me.return_value = MagicMock(data=None)
    with pytest.raises(SocialPlatformError, match="Empty user response"):
        client.get_account_data()


# --- get_post_data ---


def test_get_post_data_maps_tweet() -> None:
    client = _oauth1_client()
    tweet = _tweet(tweet_id="555", text="metrics tweet")
    client._v2.get_tweet.return_value = _single_tweet_response(tweet)

    post = client.get_post_data("555")
    assert post.id == "555"
    assert post.text == "metrics tweet"
    assert post.like_count == 5
    client._v2.get_tweet.assert_called_once()
    assert client._v2.get_tweet.call_args.kwargs["id"] == "555"


def test_get_post_data_not_found_raises() -> None:
    client = _oauth1_client()
    client._v2.get_tweet.return_value = MagicMock(data=None)
    with pytest.raises(SocialPlatformError, match="Tweet not found: 404"):
        client.get_post_data("404")


# --- search_recent_tweets ---


def test_search_recent_empty_query_returns_empty() -> None:
    client = _oauth1_client()
    assert client.search_recent_tweets("") == []
    assert client.search_recent_tweets("   ") == []
    client._v2.search_recent_tweets.assert_not_called()


def test_search_recent_maps_rows_and_clamps_max_results() -> None:
    client = _oauth1_client()
    tweet = _tweet(tweet_id="999", text="Search hit https://t.co/x")
    client._v2.search_recent_tweets.return_value = _tweet_response(tweet)

    rows = client.search_recent_tweets("#tag", max_results=5, trend_query="tag")
    assert len(rows) == 1
    assert rows[0]["id"] == "999"
    assert rows[0]["source"] == "search_recent"
    assert rows[0]["trend_query"] == "tag"
    call_kw = client._v2.search_recent_tweets.call_args
    assert call_kw.args[0] == "#tag"
    assert call_kw.kwargs["max_results"] == 10  # min clamp
    assert call_kw.kwargs["sort_order"] == "relevancy"
    assert "attachments" in call_kw.kwargs["tweet_fields"]


def test_search_recent_max_results_upper_clamp() -> None:
    client = _oauth1_client()
    client._v2.search_recent_tweets.return_value = _tweet_response()
    client.search_recent_tweets("q", max_results=500)
    assert client._v2.search_recent_tweets.call_args.kwargs["max_results"] == 100


def test_search_recent_skips_blank_text_tweets() -> None:
    client = _oauth1_client()
    empty = _tweet(text="   ")
    good = _tweet(tweet_id="2", text="ok https://t.co/y")
    client._v2.search_recent_tweets.return_value = _tweet_response(empty, good)
    rows = client.search_recent_tweets("q", max_results=10)
    assert len(rows) == 1
    assert rows[0]["id"] == "2"


# --- get_following_timeline_tweets ---


def test_following_timeline_calls_home_timeline_with_retweet_exclude() -> None:
    client = _oauth1_client()
    tweet = _tweet(tweet_id="tl1", text="Timeline https://t.co/z")
    client._v2.get_home_timeline.return_value = _tweet_response(tweet)

    rows = client.get_following_timeline_tweets(max_results=50, exclude_retweets=True)
    assert len(rows) == 1
    assert rows[0]["source"] == "following_timeline"
    kw = client._v2.get_home_timeline.call_args.kwargs
    assert kw["max_results"] == 50
    assert kw["exclude"] == ["retweets"]
    assert kw["user_auth"] is False
    assert "attachments" in kw["tweet_fields"]


def test_following_timeline_no_retweet_exclude_when_disabled() -> None:
    client = _oauth1_client()
    client._v2.get_home_timeline.return_value = _tweet_response()
    client.get_following_timeline_tweets(max_results=1, exclude_retweets=False)
    assert client._v2.get_home_timeline.call_args.kwargs["exclude"] is None


def test_following_timeline_max_results_clamped() -> None:
    client = _oauth1_client()
    client._v2.get_home_timeline.return_value = _tweet_response()
    client.get_following_timeline_tweets(max_results=0)
    assert client._v2.get_home_timeline.call_args.kwargs["max_results"] == 1
    client.get_following_timeline_tweets(max_results=999)
    assert client._v2.get_home_timeline.call_args.kwargs["max_results"] == 100


def test_following_timeline_empty_response() -> None:
    client = _oauth1_client()
    client._v2.get_home_timeline.return_value = MagicMock(data=None)
    assert client.get_following_timeline_tweets() == []


def test_oauth2_following_timeline_uses_user_auth_false() -> None:
    client = _oauth2_client()
    client._v2.get_home_timeline.return_value = _tweet_response(_tweet())
    client.get_following_timeline_tweets(max_results=10)
    assert client._v2.get_home_timeline.call_args.kwargs["user_auth"] is False


# --- _fetch_reference_tweets media expansion fallback ---


def test_fetch_reference_tweets_retries_minimal_on_403() -> None:
    client = _oauth1_client()
    ok_resp = _tweet_response(_tweet(text="retry ok https://t.co/a"))
    calls: list[dict] = []

    def fetcher(**kw):
        calls.append(dict(kw))
        if len(calls) == 1:
            raise _tweepy_error(tweepy.Forbidden, "403 Forbidden", status_code=403)
        return ok_resp

    resp = client._fetch_reference_tweets(fetcher, user_auth=True)
    assert resp is ok_resp
    assert len(calls) == 2
    assert "expansions" in calls[0]
    assert "expansions" not in calls[1]


def test_fetch_reference_tweets_non_403_reraises_wrapped() -> None:
    client = _oauth1_client()

    def fetcher(**kw):
        raise _tweepy_error(tweepy.NotFound, "missing", status_code=404)

    with pytest.raises(SocialPlatformError):
        client._fetch_reference_tweets(fetcher, user_auth=True)

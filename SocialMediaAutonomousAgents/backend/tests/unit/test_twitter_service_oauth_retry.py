"""TwitterService 401 refresh-and-retry behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import tweepy

from app.models.account import AccountDocument
from app.services.oauth_exceptions import ReauthRequired
from app.services.twitter_service import TwitterService
from app.social.credentials import XOAuth2UserCredentials
from app.social.dtos import AccountData
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from tests.unit.test_twitter_service_x import FakeRepo


def _unauthorized_error() -> SocialPlatformError:
    response = MagicMock()
    response.status_code = 401
    cause = tweepy.Unauthorized(response)
    return SocialPlatformError("X API authentication failed (401).", vendor="x", cause=cause)


def test_call_with_auth_retry_refreshes_once_on_401() -> None:
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds_v1 = XOAuth2UserCredentials(access_token="old")
    creds_v2 = XOAuth2UserCredentials(access_token="new")
    data = AccountData(id="1", username="u")

    with patch.object(tw, "_require_credentials", return_value=creds_v1) as req:
        with patch.object(tw, "_x_credentials", return_value=creds_v2) as xcreds:
            with patch.object(tw._oauth, "refresh_account_tokens", return_value=True) as refresh:
                with patch.object(
                    tw._social,
                    "get_account_data",
                    side_effect=[_unauthorized_error(), data],
                ) as gad:
                    out = tw._call_with_auth_retry(
                        acc,
                        lambda c: tw._social.get_account_data(SocialPlatform.X, c, username=None),
                    )
    assert out.username == "u"
    req.assert_called_once()
    xcreds.assert_called_once_with(acc, auto_refresh=False)
    refresh.assert_called_once_with("a1")
    assert gad.call_count == 2


def test_call_with_auth_retry_raises_when_refresh_requires_reauth() -> None:
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth2UserCredentials(access_token="old")

    with patch.object(tw, "_require_credentials", return_value=creds):
        with patch.object(
            tw._oauth,
            "refresh_account_tokens",
            side_effect=ReauthRequired("a1"),
        ):
            with patch.object(
                tw._social,
                "get_account_data",
                side_effect=_unauthorized_error(),
            ):
                with pytest.raises(ValueError, match="re-authorization"):
                    tw._call_with_auth_retry(
                        acc,
                        lambda c: tw._social.get_account_data(SocialPlatform.X, c, username=None),
                    )

from unittest.mock import MagicMock, patch

import pytest

from app.models.account import AccountDocument
from app.services.twitter_service import TwitterService
from app.social.credentials import XOAuth1Credentials, XOAuth2UserCredentials
from app.social.dtos import CreatedPost
from app.social.service import SocialPlatform


class FakeRepo:
    def __init__(self, acc: AccountDocument | None) -> None:
        self._acc = acc

    def load(self, account_id: str) -> AccountDocument | None:
        if self._acc is not None and self._acc.account_id == account_id:
            return self._acc.model_copy(deep=True)
        return None


def test_post_tweet_oauth1_uses_create_post():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth1Credentials(
        consumer_key="k",
        consumer_secret="s",
        access_token="t",
        access_token_secret="ts",
    )
    with (
        patch.object(TwitterService, "_x_credentials", return_value=creds),
        patch.object(tw._social, "create_post", return_value=CreatedPost(id="99", text="hello")) as cp,
    ):
        out = tw.post_tweet("a1", "hello")
    assert out == {"id": "99", "text": "hello"}
    cp.assert_called_once_with(SocialPlatform.X, creds, "hello")


def test_post_tweet_oauth2_uses_create_post():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth2UserCredentials(access_token="bearer-user-token")
    with (
        patch.object(TwitterService, "_x_credentials", return_value=creds),
        patch.object(tw._social, "create_post", return_value=CreatedPost(id="88", text="x")) as cp,
    ):
        out = tw.post_tweet("a1", "x")
    assert out["id"] == "88"
    cp.assert_called_once()


def test_post_tweet_requires_credentials():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    with patch.object(TwitterService, "_x_credentials", return_value=None):
        with pytest.raises(ValueError, match="Missing or invalid X credentials"):
            tw.post_tweet("a1", "hi")

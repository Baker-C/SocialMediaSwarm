from unittest.mock import MagicMock, patch

from app.models.account import AccountDocument
from app.services.twitter_service import TwitterService
from app.social.credentials import XOAuth2UserCredentials
from app.social.exceptions import SocialPlatformError


class FakeRepo:
    def __init__(self, acc: AccountDocument | None) -> None:
        self._acc = acc

    def load(self, account_id: str) -> AccountDocument | None:
        if self._acc is not None and self._acc.account_id == account_id:
            return self._acc.model_copy(deep=True)
        return None


def test_verify_api_health_missing_account():
    tw = TwitterService(repo=FakeRepo(None))
    assert tw.verify_api_health("nope") == ["RavenDB: no account document for account_id='nope'"]


def test_verify_api_health_missing_x_credentials():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    errs = tw.verify_api_health("a1")
    assert len(errs) == 1
    assert "missing" in errs[0].lower() or "oauth" in errs[0].lower()


def test_verify_api_health_x_api_failure():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth2UserCredentials(access_token="tok")
    tw._social = MagicMock()
    tw._social.get_account_data.side_effect = SocialPlatformError("401", vendor="x")
    with patch.object(TwitterService, "_x_credentials", return_value=creds):
        errs = tw.verify_api_health("a1")
    assert len(errs) == 1
    assert errs[0].startswith("X API:")
    assert "401" in errs[0]


def test_verify_api_health_all_clear():
    acc = AccountDocument(account_id="a1", niche="n")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth2UserCredentials(access_token="tok")
    tw._social = MagicMock()
    with patch.object(TwitterService, "_x_credentials", return_value=creds):
        assert tw.verify_api_health("a1") == []

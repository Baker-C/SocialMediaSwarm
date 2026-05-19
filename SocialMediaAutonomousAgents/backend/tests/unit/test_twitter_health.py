from unittest.mock import MagicMock, patch

from app.models.account import AccountDocument
from app.services.twitter_service import TwitterService
from app.social.credentials import XOAuth1Credentials
from app.social.exceptions import SocialPlatformError


class FakeRepo:
    def __init__(self, acc: AccountDocument | None) -> None:
        self._acc = acc

    def load(self, account_id: str) -> AccountDocument | None:
        if self._acc is not None and self._acc.account_id == account_id:
            return self._acc.model_copy(deep=True)
        return None


def test_verify_x_connection_missing_document():
    tw = TwitterService(repo=FakeRepo(None))
    ok, msg = tw.verify_x_connection("nobody")
    assert ok is False
    assert "no account document" in msg.lower()


def test_verify_x_connection_social_platform_error_includes_cause():
    acc = AccountDocument(account_id="u1", niche="t")
    tw = TwitterService(repo=FakeRepo(acc))
    creds = XOAuth1Credentials(
        consumer_key="a",
        consumer_secret="b",
        access_token="c",
        access_token_secret="d",
    )
    tw._social = MagicMock()
    tw._social.get_account_data.side_effect = SocialPlatformError(
        "401 Unauthorized", vendor="x", cause=RuntimeError("inner")
    )
    with patch.object(TwitterService, "_x_credentials", return_value=creds):
        ok, msg = tw.verify_x_connection("u1")
    assert ok is False
    assert "401" in msg
    assert "underlying" in msg

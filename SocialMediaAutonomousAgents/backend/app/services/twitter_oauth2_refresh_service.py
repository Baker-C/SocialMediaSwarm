"""Backward-compatible wrapper around ``TwitterOAuth2Service`` refresh APIs."""

from __future__ import annotations

from app.services.twitter_oauth2_service import RefreshResult, TwitterOAuth2Service

TOKEN_ENDPOINT = "https://api.x.com/2/oauth2/token"


class TwitterOAuth2RefreshService(TwitterOAuth2Service):
    """Deprecated alias; use ``TwitterOAuth2Service`` directly."""

    def refresh_active_accounts(self, *, batch_size: int) -> RefreshResult:
        return self.refresh_all_tokens(batch_size=batch_size)

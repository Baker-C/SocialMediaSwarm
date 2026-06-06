"""Scheduled OAuth2 token refresh for all connected accounts."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.twitter_oauth2_service import TwitterOAuth2Service

logger = logging.getLogger(__name__)


def run_oauth2_refresh_job() -> None:
    if not settings.oauth2_refresh_enabled:
        logger.debug("oauth2_refresh_job: disabled")
        return
    svc = TwitterOAuth2Service()
    svc.purge_expired_sessions()
    res = svc.refresh_all_tokens(batch_size=settings.oauth2_refresh_batch_size)
    logger.info(
        "oauth2_refresh_job: refreshed=%s skipped=%s failed=%s",
        res.refreshed,
        res.skipped_no_refresh,
        res.failed,
    )

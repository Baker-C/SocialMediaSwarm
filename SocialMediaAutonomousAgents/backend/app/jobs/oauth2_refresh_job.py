"""Background job to refresh OAuth2 tokens for active accounts."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.twitter_oauth2_refresh_service import TwitterOAuth2RefreshService

logger = logging.getLogger(__name__)


def run_oauth2_refresh_job() -> None:
    if not settings.oauth2_refresh_enabled:
        return
    svc = TwitterOAuth2RefreshService()
    out = svc.refresh_active_accounts(batch_size=settings.oauth2_refresh_batch_size)
    logger.info(
        "oauth2_refresh: refreshed=%s skipped_no_refresh=%s failed=%s",
        out.refreshed,
        out.skipped_no_refresh,
        out.failed,
    )


"""
Live RavenDB + external API health (X ``get_me`` when decryptable credentials exist).

Opt-in — set **one** of these (``API_HEALTH_CHECK`` is preferred)::

    set API_HEALTH_CHECK=1
    pytest tests/integration/test_api_health.py -v --log-cli-level=WARNING

Legacy alias: ``TWITTER_API_HEALTH_CHECK=1`` (same behavior).
"""

from __future__ import annotations

import logging
import os
import warnings

import pytest

from app.services.account_repository import AccountRepository
from app.services.twitter_service import TwitterService


def _api_health_check_enabled() -> bool:
    for key in ("API_HEALTH_CHECK", "TWITTER_API_HEALTH_CHECK"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


@pytest.mark.skipif(
    not _api_health_check_enabled(),
    reason=(
        "Set API_HEALTH_CHECK=1 (or legacy TWITTER_API_HEALTH_CHECK=1) to run live "
        "RavenDB + X API checks for all accounts."
    ),
)
def test_api_connection_health_all_accounts():
    repo = AccountRepository()
    tw = TwitterService(repo)
    accounts = repo.list_all_accounts()
    assert accounts, "No account documents returned from RavenDB (list_all_accounts is empty)"

    log = logging.getLogger("test_api_health")
    failures: list[str] = []

    for acc in accounts:
        for detail in tw.verify_api_health(acc.account_id):
            line = f"account_id={acc.account_id!r} ({acc.twitter_handle or 'no handle'}): {detail}"
            failures.append(line)
            log.warning("API health FAILED - %s", line)
            warnings.warn(f"API health FAILED - {line}", UserWarning, stacklevel=1)

    assert not failures, "API health check failed for one or more accounts:\n" + "\n".join(failures)

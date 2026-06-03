"""RavenDB-backed reads with safe fallbacks for collections not yet migrated."""

import logging
from collections import Counter

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository

logger = logging.getLogger(__name__)


def _account_has_x_credentials(acc: AccountDocument) -> bool:
    return bool((acc.credentials.oauth2_access_token_enc or "").strip())


def _account_public(acc: AccountDocument) -> dict:
    follower_growth = None
    if acc.followers_when_registered is not None:
        follower_growth = acc.followers - acc.followers_when_registered

    recent_post = None
    if acc.last_post_text or acc.last_post_at:
        text = (acc.last_post_text or "").strip()
        recent_post = {
            "snippet": text[:200] + ("…" if len(text) > 200 else ""),
            "posted_at": acc.last_post_at,
            "post_id": acc.last_post_id,
            "views": acc.last_post_views,
        }

    return {
        "account_id": acc.account_id,
        "niche": acc.niche,
        "twitter_handle": acc.twitter_handle,
        "status": acc.status,
        "followers": acc.followers,
        "posts_total": acc.posts_total,
        "has_credentials": _account_has_x_credentials(acc),
        "registered_at": acc.registered_at,
        "follower_growth_vs_registered": follower_growth,
        "last_interval_slot": acc.last_interval_slot,
        "recent_post": recent_post,
    }


class RavenDBService:
    def __init__(self, account_repo: AccountRepository | None = None) -> None:
        self._accounts = account_repo or AccountRepository()

    def get_accounts(self) -> list[dict]:
        try:
            rows = self._accounts.list_all_accounts()
            return [_account_public(a) for a in rows]
        except RavenDBHttpError as exc:
            logger.warning("RavenDB unavailable for accounts: %s", exc)
            return []

    def get_account(self, account_id: str) -> dict | None:
        try:
            acc = self._accounts.load(account_id)
            if acc is None:
                return None
            return _account_public(acc)
        except RavenDBHttpError as exc:
            logger.warning("RavenDB unavailable for account %s: %s", account_id, exc)
            return None

    def get_posts(self) -> list[dict]:
        return []

    def get_patterns(self) -> list[dict]:
        return []

    def get_metrics(self, account_id: str) -> dict:
        return {"account_id": account_id, "avg_engagement_rate": 0.0, "health_score": 0}

    def get_dashboard(self):
        try:
            accs = self._accounts.list_active()
            active = len(accs)
            if not accs:
                return {"active_accounts": 0, "top_niche": "n/a", "avg_engagement": 0.0}
            top_niche = Counter(a.niche for a in accs).most_common(1)[0][0]
            return {
                "active_accounts": active,
                "top_niche": top_niche,
                "avg_engagement": 0.0,
            }
        except RavenDBHttpError:
            return {"active_accounts": 0, "top_niche": "n/a", "avg_engagement": 0.0}

"""RavenDB-backed reads with safe fallbacks for collections not yet migrated."""

import logging
from collections import Counter
from datetime import datetime, timezone

from app.infrastructure.ravendb_http import RavenDBHttpError, get_ravendb_client
from app.models.account import AccountDocument
from app.models.metrics import AccountMetricsDocument
from app.models.tracked_post import TrackedPostDocument
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.twitter_oauth2_service import TwitterOAuth2Service

logger = logging.getLogger(__name__)


def _account_has_x_credentials(acc: AccountDocument, oauth: TwitterOAuth2Service | None = None) -> bool:
    svc = oauth or TwitterOAuth2Service()
    return svc.is_connected(acc.account_id)


def _account_public(acc: AccountDocument, oauth: TwitterOAuth2Service | None = None) -> dict:
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
        "has_credentials": _account_has_x_credentials(acc, oauth),
        "registered_at": acc.registered_at,
        "follower_growth_vs_registered": follower_growth,
        "last_interval_slot": acc.last_interval_slot,
        "recent_post": recent_post,
        "voice_version_label": acc.voice_version_label,
        "voice_version_seq": acc.voice_version_seq,
        "search_queries_count": len(acc.search_queries),
        "copied_reference_count": len(acc.copied_reference_tweet_ids),
    }


class RavenDBService:
    def __init__(
        self,
        account_repo: AccountRepository | None = None,
        oauth: TwitterOAuth2Service | None = None,
    ) -> None:
        self._accounts = account_repo or AccountRepository()
        self._oauth = oauth or TwitterOAuth2Service(account_repo=self._accounts)
        self._tracked = TrackedPostRepository()

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
            return _account_public(acc, self._oauth)
        except RavenDBHttpError as exc:
            logger.warning("RavenDB unavailable for account %s: %s", account_id, exc)
            return None

    def get_posts(self, *, limit_per_account: int = 10) -> list[dict]:
        """Recent tracked posts across active accounts (fleet rollup)."""
        cap = max(1, min(int(limit_per_account), 100))
        try:
            accs = self._accounts.list_active()
        except RavenDBHttpError as exc:
            logger.warning("RavenDB unavailable for fleet posts: %s", exc)
            return []
        out: list[dict] = []
        for acc in accs:
            try:
                rows = self._tracked.list_for_account(acc.account_id, limit=cap)
            except RavenDBHttpError:
                continue
            for raw in rows:
                try:
                    stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
                    doc = TrackedPostDocument.model_validate(stripped)
                    out.append(doc.model_dump(exclude_none=True))
                except Exception:
                    continue
        out.sort(key=lambda r: str(r.get("posted_at") or ""), reverse=True)
        return out

    def get_patterns(self) -> list[dict]:
        return []

    def _load_account_metrics(self, account_id: str) -> AccountMetricsDocument | None:
        try:
            raw = get_ravendb_client().get_document(AccountMetricsDocument.document_id(account_id))
        except RavenDBHttpError:
            return None
        if raw is None:
            return None
        try:
            stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            return AccountMetricsDocument.model_validate(stripped)
        except Exception:
            return None

    def get_metrics(self, account_id: str) -> dict:
        try:
            rows = self._tracked.list_for_account(account_id)
        except RavenDBHttpError:
            rows = []
        engagement = [r.get("engagement_rate") for r in rows if isinstance(r.get("engagement_rate"), (int, float))]
        follower_delta = [r.get("follower_delta") for r in rows if isinstance(r.get("follower_delta"), int)]
        reply_rates = [r.get("reply_rate") for r in rows if isinstance(r.get("reply_rate"), (int, float))]
        like_rates = [r.get("like_rate") for r in rows if isinstance(r.get("like_rate"), (int, float))]
        result: dict = {
            "account_id": account_id,
            "tracked_posts": len(rows),
            "avg_engagement_rate": _avg(engagement) or 0.0,
            "avg_follower_delta": _avg(follower_delta),
            "avg_reply_rate": _avg(reply_rates),
            "avg_like_rate": _avg(like_rates),
        }
        metrics_doc = self._load_account_metrics(account_id)
        if metrics_doc is not None:
            result.update(metrics_doc.model_dump(exclude_none=True))
            result["tracked_posts"] = len(rows)
        return result

    def get_account_metrics(self, account_id: str) -> dict | None:
        doc = self._load_account_metrics(account_id)
        if doc is None:
            return None
        return doc.model_dump(exclude_none=True)

    def get_dashboard(self):
        computed_at = datetime.now(timezone.utc).isoformat()
        try:
            accs = self._accounts.list_active()
            active = len(accs)
            if not accs:
                return {
                    "active_accounts": 0,
                    "top_niche": "n/a",
                    "avg_engagement": 0.0,
                    "total_tracked_posts": 0,
                    "avg_reply_rate": 0.0,
                    "accounts_without_posts": 0,
                    "computed_at": computed_at,
                }
            top_niche = Counter(a.niche for a in accs).most_common(1)[0][0]
            all_engagement: list[float] = []
            all_reply_rates: list[float] = []
            total_tracked = 0
            accounts_without_posts = 0
            for a in accs:
                rows = self._tracked.list_for_account(a.account_id)
                if not rows:
                    accounts_without_posts += 1
                total_tracked += len(rows)
                all_engagement.extend(
                    [float(r.get("engagement_rate")) for r in rows if isinstance(r.get("engagement_rate"), (int, float))]
                )
                all_reply_rates.extend(
                    [float(r.get("reply_rate")) for r in rows if isinstance(r.get("reply_rate"), (int, float))]
                )
            return {
                "active_accounts": active,
                "top_niche": top_niche,
                "avg_engagement": _avg(all_engagement) or 0.0,
                "total_tracked_posts": total_tracked,
                "avg_reply_rate": _avg(all_reply_rates) or 0.0,
                "accounts_without_posts": accounts_without_posts,
                "computed_at": computed_at,
            }
        except RavenDBHttpError:
            return {
                "active_accounts": 0,
                "top_niche": "n/a",
                "avg_engagement": 0.0,
                "total_tracked_posts": 0,
                "avg_reply_rate": 0.0,
                "accounts_without_posts": 0,
                "computed_at": computed_at,
            }


def _avg(values: list[int | float]) -> float | None:
    if not values:
        return None
    return float(sum(float(v) for v in values)) / float(len(values))

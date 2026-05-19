import logging

from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.twitter_service import TwitterService

logger = logging.getLogger(__name__)


def run_engagement_job() -> dict:
    """Poll X for metrics on tracked posts; refresh account.last_post_views when possible."""
    repo = AccountRepository()
    trepo = TrackedPostRepository()
    tw = TwitterService(repo)
    rows: list[dict] = []
    for acc in repo.list_active():
        aid = acc.account_id
        tweet_ids = trepo.list_tweet_ids(aid)
        if not tweet_ids:
            rows.append({"account_id": aid, "status": "no_tracked_posts"})
            continue
        updated = 0
        last_err: str | None = None
        for tid in tweet_ids:
            try:
                m = tw.get_tweet_metrics(aid, tid)
                trepo.update_metrics(aid, tid, m)
                updated += 1
            except Exception as exc:
                last_err = str(exc)
                logger.warning("engagement_job metrics %s %s: %s", aid, tid, exc)
        status = "ok" if updated else "partial_or_failed"
        if updated == 0 and last_err:
            status = "partial_or_failed"
        fresh = repo.load(aid)
        if fresh and fresh.last_post_id and fresh.last_post_id in tweet_ids:
            try:
                m = tw.get_tweet_metrics(aid, fresh.last_post_id)
                imp = m.get("impression_count")
                if isinstance(imp, int):
                    data = fresh.model_dump()
                    data["last_post_views"] = imp
                    repo.save(AccountDocument.model_validate(data))
            except Exception as exc:
                last_err = str(exc)
                logger.warning("engagement_job account last_post_views %s: %s", aid, exc)
        rows.append(
            {
                "account_id": aid,
                "status": status,
                "posts_polled": updated,
                "error": last_err,
            }
        )
    logger.debug("engagement_job: %d accounts", len(rows))
    return {"accounts_checked": len(rows), "detail": rows}

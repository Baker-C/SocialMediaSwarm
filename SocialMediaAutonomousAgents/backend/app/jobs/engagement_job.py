import logging
from datetime import datetime, timezone

from app.models.account import AccountDocument
from app.models.post_metric_snapshot import PostMetricSnapshotDocument
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.post_metric_snapshot_repository import PostMetricSnapshotRepository
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.twitter_service import TwitterService
from app.metrics.derived import compute_rates

logger = logging.getLogger(__name__)


def run_engagement_job() -> dict:
    """Poll X for metrics on tracked posts; refresh account.last_post_views when possible."""
    repo = AccountRepository()
    trepo = TrackedPostRepository()
    tw = TwitterService(repo)
    snapshots = PostMetricSnapshotRepository()
    outcomes = PipelineOutcomeRepository()
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
                m["follower_delta"] = account_follower_delta(acc)
                m.update(compute_rates(m))
                trepo.update_metrics(aid, tid, m)
                rate = m.get("engagement_rate")
                reply_rate = m.get("reply_rate")
                like_rate = m.get("like_rate")
                snapshots.save(
                    PostMetricSnapshotDocument(
                        account_id=aid,
                        tweet_id=tid,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        like_count=m.get("like_count"),
                        reply_count=m.get("reply_count"),
                        retweet_count=m.get("retweet_count"),
                        quote_count=m.get("quote_count"),
                        impression_count=m.get("impression_count"),
                        profile_click_count=m.get("profile_click_count"),
                        engagement_rate=rate if isinstance(rate, float) else None,
                        reply_rate=reply_rate if isinstance(reply_rate, float) else None,
                        like_rate=like_rate if isinstance(like_rate, float) else None,
                        engagement_velocity=m.get("engagement_velocity"),
                    )
                )
                updated += 1
            except Exception as exc:
                last_err = str(exc)
                logger.warning("engagement_job metrics %s %s: %s", aid, tid, exc)
                if "402" in last_err:
                    outcomes.append(
                        account_id=aid,
                        phase="engagement_job",
                        status="partial_or_failed",
                        reason="x_metrics_402",
                        details={"tweet_id": tid, "error": last_err},
                    )
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
        outcomes.append(
            account_id=aid,
            phase="engagement_job",
            status=status,
            reason=last_err,
            details={"posts_polled": updated},
        )
    logger.debug("engagement_job: %d accounts", len(rows))
    return {"accounts_checked": len(rows), "detail": rows}


def account_follower_delta(acc: AccountDocument) -> int | None:
    followers = acc.followers
    if acc.followers_when_registered is None:
        return None
    return int(followers) - int(acc.followers_when_registered)

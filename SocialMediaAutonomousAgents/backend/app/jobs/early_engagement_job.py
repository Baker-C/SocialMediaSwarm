"""High-frequency polling for newly posted tweets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.jobs.engagement_job import account_follower_delta
from app.metrics.derived import compute_rates, compute_velocity
from app.models.post_metric_snapshot import PostMetricSnapshotDocument
from app.services.account_repository import AccountRepository
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.post_metric_snapshot_repository import PostMetricSnapshotRepository
from app.services.post_registry import TrackedPostRepository
from app.services.twitter_service import TwitterService


def run_early_engagement_job() -> dict:
    repo = AccountRepository()
    trepo = TrackedPostRepository()
    tw = TwitterService(repo)
    snapshots = PostMetricSnapshotRepository()
    outcomes = PipelineOutcomeRepository()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(settings.early_engagement_window_hours)))
    checked = 0
    updated = 0
    for acc in repo.list_active():
        rows = trepo.list_for_account(acc.account_id)
        for row in rows:
            posted_at = str(row.get("posted_at") or "")
            if not posted_at:
                continue
            try:
                posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if posted_dt < cutoff:
                continue
            tid = str(row.get("tweet_id") or "")
            if not tid:
                continue
            checked += 1
            try:
                m = tw.get_tweet_metrics(acc.account_id, tid)
                m["follower_delta"] = account_follower_delta(acc)
                rates = compute_rates(m)
                m.update(rates)
                prev = snapshots.latest_for_tweet(acc.account_id, tid)
                curr_snapshot = {
                    "like_count": m.get("like_count"),
                    "reply_count": m.get("reply_count"),
                    "retweet_count": m.get("retweet_count"),
                    "quote_count": m.get("quote_count"),
                    "impression_count": m.get("impression_count"),
                }
                m["engagement_velocity"] = compute_velocity(prev.model_dump() if prev else None, curr_snapshot)
                trepo.update_metrics(acc.account_id, tid, m)
                snapshots.save(
                    PostMetricSnapshotDocument(
                        account_id=acc.account_id,
                        tweet_id=tid,
                        captured_at=datetime.now(timezone.utc).isoformat(),
                        like_count=m.get("like_count"),
                        reply_count=m.get("reply_count"),
                        retweet_count=m.get("retweet_count"),
                        quote_count=m.get("quote_count"),
                        impression_count=m.get("impression_count"),
                        profile_click_count=m.get("profile_click_count"),
                        engagement_rate=m.get("engagement_rate"),
                        reply_rate=m.get("reply_rate"),
                        like_rate=m.get("like_rate"),
                        engagement_velocity=m.get("engagement_velocity"),
                    )
                )
                updated += 1
            except Exception as exc:
                outcomes.append(
                    account_id=acc.account_id,
                    phase="early_engagement_job",
                    status="partial_or_failed",
                    reason=str(exc),
                    details={"tweet_id": tid},
                )
        outcomes.append(account_id=acc.account_id, phase="early_engagement_job", status="ok")
    return {"checked": checked, "updated": updated}

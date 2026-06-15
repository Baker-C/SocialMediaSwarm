from fastapi import APIRouter, HTTPException, Query

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.models.tracked_post import TrackedPostDocument
from app.services.account_repository import AccountRepository
from app.services.pipeline_outcome_repository import PipelineOutcomeRepository
from app.services.post_metric_snapshot_repository import PostMetricSnapshotRepository
from app.services.post_registry import TrackedPostRepository
from app.services.ravendb_service import RavenDBService
from app.services.voice_revision_repository import VoiceRevisionRepository

router = APIRouter()
repo = AccountRepository()
tracked_posts = TrackedPostRepository()
post_snapshots = PostMetricSnapshotRepository()
pipeline_outcomes = PipelineOutcomeRepository()
voice_revisions = VoiceRevisionRepository()
service = RavenDBService()


def _require_account(account_id: str):
    try:
        acc = repo.load(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB unavailable: {exc}") from exc
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.get("/accounts/{account_id}/tracked-posts")
def list_tracked_posts_for_account(
    account_id: str,
    limit: int = Query(default=500, ge=1, le=500),
    since: str | None = Query(default=None, description="ISO timestamp; only posts at or after this time"),
):
    _require_account(account_id)
    try:
        rows = tracked_posts.list_for_account(account_id, limit=limit, since=since)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    posts = []
    for raw in rows:
        try:
            stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            posts.append(TrackedPostDocument.model_validate(stripped).model_dump(exclude_none=True))
        except Exception:
            continue
    return {"account_id": account_id, "count": len(posts), "posts": posts}


@router.get("/accounts/{account_id}/posts/{tweet_id}")
def get_tracked_post(account_id: str, tweet_id: str):
    _require_account(account_id)
    try:
        raw = tracked_posts.get_for_tweet(account_id, tweet_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    if raw is None:
        raise HTTPException(status_code=404, detail="Tracked post not found")
    try:
        return TrackedPostDocument.model_validate(raw).model_dump(exclude_none=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invalid tracked post document") from exc


@router.get("/accounts/{account_id}/posts/{tweet_id}/snapshots")
def list_post_snapshots(
    account_id: str,
    tweet_id: str,
    limit: int = Query(default=500, ge=1, le=500),
):
    _require_account(account_id)
    try:
        rows = post_snapshots.list_for_tweet(account_id, tweet_id, limit=limit)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    snapshots = [r.model_dump(exclude_none=True) for r in rows]
    return {"account_id": account_id, "tweet_id": tweet_id, "count": len(snapshots), "snapshots": snapshots}


@router.get("/accounts/{account_id}/account-metrics")
def get_account_metrics(account_id: str):
    _require_account(account_id)
    try:
        metrics = service.get_account_metrics(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    if metrics is None:
        raise HTTPException(status_code=404, detail="Account metrics not found")
    return metrics


@router.get("/accounts/{account_id}/pipeline-outcomes")
def list_pipeline_outcomes(
    account_id: str,
    since: str | None = Query(default=None, description="ISO timestamp; only outcomes at or after this time"),
    limit: int = Query(default=200, ge=1, le=500),
    phase: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    _require_account(account_id)
    try:
        rows = pipeline_outcomes.list_for_account(
            account_id, since=since, limit=limit, phase=phase, status=status
        )
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    outcomes = [r.model_dump(exclude_none=True) for r in rows]
    return {"account_id": account_id, "count": len(outcomes), "outcomes": outcomes}


@router.get("/accounts/{account_id}/voice-revisions")
def list_voice_revisions(account_id: str):
    _require_account(account_id)
    try:
        rows = voice_revisions.list_for_account(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    revisions = [r.model_dump(exclude_none=True) for r in rows]
    return {"account_id": account_id, "count": len(revisions), "revisions": revisions}


@router.get("/pipeline-outcomes")
def list_fleet_pipeline_outcomes(
    since: str | None = Query(default=None, description="ISO timestamp; only outcomes at or after this time"),
    limit: int = Query(default=200, ge=1, le=500),
    account_id: str | None = Query(default=None, description="Optional account filter"),
    phase: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    if account_id is not None:
        _require_account(account_id)
    try:
        rows = pipeline_outcomes.list_fleet(
            since=since, limit=limit, account_id=account_id, phase=phase, status=status
        )
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    outcomes = [r.model_dump(exclude_none=True) for r in rows]
    return {"count": len(outcomes), "outcomes": outcomes}

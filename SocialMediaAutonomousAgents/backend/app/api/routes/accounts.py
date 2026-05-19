from fastapi import APIRouter, HTTPException, Query

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.account_update_service import AccountUpdateBody, account_edit_view, apply_account_update
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.ravendb_service import RavenDBService
from app.services.twitter_service import TwitterService

router = APIRouter()
service = RavenDBService()
repo = AccountRepository()
pulled_tweets = PulledTweetRepository()


@router.get("/accounts")
def get_accounts():
    return service.get_accounts()


@router.get("/accounts/{account_id}")
def get_account(account_id: str):
    row = service.get_account(account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return row


@router.get("/accounts/{account_id}/edit")
def get_account_for_edit(account_id: str):
    """Non-secret fields and metadata for the dashboard update-account form."""
    try:
        acc = repo.load(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB unavailable: {exc}") from exc
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account_edit_view(acc)


@router.patch("/accounts/{account_id}", status_code=200)
def patch_account(account_id: str, body: AccountUpdateBody):
    try:
        acc = apply_account_update(account_id, body, repo=repo)
    except LookupError:
        raise HTTPException(status_code=404, detail="Account not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    return {"ok": True, "account_id": acc.account_id}


@router.patch("/accounts/{account_id}/archive")
def archive_account(account_id: str):
    existing = repo.load(account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Account not found")
    data = existing.model_dump()
    data["status"] = "inactive"
    repo.save(AccountDocument.model_validate(data))
    return {"account_id": account_id, "status": "inactive"}


@router.delete("/accounts/{account_id}")
def delete_account(account_id: str):
    return archive_account(account_id)


@router.get("/accounts/{account_id}/pulled-tweets")
def list_pulled_tweets_for_account(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    since: str | None = Query(default=None, description="ISO timestamp; only tweets pulled at or after this time"),
):
    """Reference tweets previously pulled for this account's post pipeline."""
    try:
        acc = repo.load(account_id)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB unavailable: {exc}") from exc
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        rows = pulled_tweets.list_for_account(account_id, limit=limit, since=since)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    tweets = [r.model_dump(exclude_none=True) for r in rows]
    return {"account_id": account_id, "count": len(tweets), "tweets": tweets}


@router.get("/accounts/{account_id}/status")
def account_status(account_id: str):
    acc = repo.load(account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {
        "account_id": acc.account_id,
        "status": acc.status,
        "last_post_slot": acc.last_post_slot,
        "posts_total": acc.posts_total,
    }


@router.post("/accounts/{account_id}/test")
def account_test_post(account_id: str):
    tw = TwitterService(repo)
    text = f"Credential test ping ({account_id})"
    try:
        out = tw.post_tweet(account_id, text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": out}

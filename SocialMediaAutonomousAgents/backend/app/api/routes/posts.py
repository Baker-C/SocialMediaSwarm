from fastapi import APIRouter, Query

from app.services.ravendb_service import RavenDBService

router = APIRouter()
service = RavenDBService()


@router.get("/posts")
def get_posts(limit_per_account: int = Query(default=10, ge=1, le=100)):
    posts = service.get_posts(limit_per_account=limit_per_account)
    return {"count": len(posts), "posts": posts}

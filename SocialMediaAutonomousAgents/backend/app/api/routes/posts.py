from fastapi import APIRouter

from app.services.ravendb_service import RavenDBService

router = APIRouter()
service = RavenDBService()


@router.get("/posts")
def get_posts():
    return service.get_posts()

from fastapi import APIRouter

from app.services.ravendb_service import RavenDBService

router = APIRouter()
service = RavenDBService()


@router.get("/patterns")
def get_patterns():
    return service.get_patterns()

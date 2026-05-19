from fastapi import APIRouter

from app.services.ravendb_service import RavenDBService

router = APIRouter()
service = RavenDBService()


@router.get("/dashboard")
def get_dashboard():
    return service.get_dashboard()

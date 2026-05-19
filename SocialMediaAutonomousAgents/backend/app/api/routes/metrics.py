from fastapi import APIRouter

from app.services.ravendb_service import RavenDBService

router = APIRouter()
service = RavenDBService()


@router.get("/metrics/{account_id}")
def get_metrics(account_id: str):
    return service.get_metrics(account_id)

from app.services.ravendb_service import RavenDBService


def test_get_accounts_returns_list():
    service = RavenDBService()
    assert isinstance(service.get_accounts(), list)

from app.core.config import settings


class RavenDBClient:
    def __init__(self) -> None:
        self.url = settings.ravendb_url
        self.db = settings.ravendb_db


client = RavenDBClient()

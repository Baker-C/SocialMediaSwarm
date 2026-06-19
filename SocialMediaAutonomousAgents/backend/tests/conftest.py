import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes.auth import require_auth


def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_dashboard_auth():
    """Bypass the dashboard auth gate for the whole test suite.

    Protected routers are mounted with ``dependencies=[Depends(require_auth)]`` and the
    gate is live whenever ``DASHBOARD_PASSWORD`` is set (it is, via .env). Route tests
    exercise route LOGIC (404s, payload shapes), not the auth gate, so without this they
    all 401 before reaching the handler. There is no dedicated dashboard-auth test that
    needs the gate enforced, so override the dependency to a no-op globally."""
    app.dependency_overrides[require_auth] = lambda: None
    yield
    app.dependency_overrides.pop(require_auth, None)

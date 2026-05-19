from fastapi.testclient import TestClient

from app.main import app


def client():
    return TestClient(app)

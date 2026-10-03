"""Health endpoint tests."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_success():
    """Verify that GET /api/v1/health returns status 200 and expected health payload with models availability."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "sonar-backend"
    assert "models" in data
    assert data["models"]["cylinder"] == "available"
    assert data["models"]["ghostvision"] == "available"
    assert data["models"]["mine"] == "available"
    assert data["models"]["shipwreck"] == "available"
    assert data["models"]["subpipe"] == "available"
    assert data["models"]["natural_seabed"] == "available"


def test_root_endpoint():
    """Verify that GET / returns status 200 with service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "sonar-backend"
    assert "health" in data

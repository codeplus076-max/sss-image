"""Tests for asynchronous analysis job processing and polling."""

import io
from fastapi import status
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.main import create_application


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


@pytest.fixture
def dummy_sonar_png():
    img = Image.new("L", (320, 240), color=50)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def test_submit_async_job_success(client, dummy_sonar_png):
    """Test submitting a valid survey image to /jobs returns 202 with job_id."""
    files = {"image": ("survey_sample.png", dummy_sonar_png, "image/png")}
    data = {
        "selected_models": "shipwreck",
        "confidence": "0.20",
        "latitude": "34.05",
        "longitude": "-118.25",
    }
    response = client.post("/api/v1/analysis/jobs", files=files, data=data)
    assert response.status_code == status.HTTP_202_ACCEPTED
    payload = response.json()
    assert "job_id" in payload
    assert payload["job_id"].startswith("JOB-")
    assert payload["poll_url"].endswith(payload["job_id"])


def test_submit_async_job_invalid_confidence(client, dummy_sonar_png):
    """Test validation errors reject immediately with 400."""
    files = {"image": ("sample.png", dummy_sonar_png, "image/png")}
    data = {"confidence": "1.5"}
    response = client.post("/api/v1/analysis/jobs", files=files, data=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_nonexistent_job(client):
    """Test polling an unknown job_id returns 404."""
    response = client.get("/api/v1/analysis/jobs/JOB-UNKNOWN12345")
    assert response.status_code == status.HTTP_404_NOT_FOUND

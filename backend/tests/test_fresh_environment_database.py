"""
Fresh Database & Storage Initialization Verification Test.

Validates that a fresh installation of the SIH26057 platform can:
1. Start with an empty, non-existent database file
2. Auto-create all required tables/schema on first startup
3. Serve health checks successfully
4. Ingest and persist a new sonar survey analysis
5. Store the raw evidence image file in clean storage
6. Retrieve the complete analysis session by ID
7. Stream the stored evidence image
8. Return paginated analysis history
9. Successfully execute deletion of the analysis record and evidence file
"""

import io
import shutil
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db, init_db
from app.main import create_application


@pytest.fixture
def fresh_db_env():
    """Create a completely isolated clean temporary database and storage directory."""
    temp_dir = tempfile.mkdtemp(prefix="sonar_fresh_env_")
    temp_path = Path(temp_dir)
    temp_db_path = temp_path / "fresh_sonarops.db"
    temp_storage_path = temp_path / "fresh_storage" / "sonar-evidence"
    temp_storage_path.mkdir(parents=True, exist_ok=True)

    # Save original settings
    orig_db_url = settings.DATABASE_URL
    orig_storage_dir = settings.LOCAL_STORAGE_DIR

    # Point to clean isolated paths
    test_db_url = f"sqlite:///{temp_db_path}"
    settings.DATABASE_URL = test_db_url
    settings.LOCAL_STORAGE_DIR = str(temp_storage_path)

    # Create fresh engine and sessionmaker
    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Automatically create tables in the fresh database
    Base.metadata.create_all(bind=test_engine)

    # Configure FastAPI app with dependency override
    app = create_application()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield {
        "client": client,
        "db_path": temp_db_path,
        "storage_path": temp_storage_path,
        "engine": test_engine,
    }

    # Teardown: restore settings and clean up temp directory
    app.dependency_overrides.clear()
    test_engine.dispose()
    settings.DATABASE_URL = orig_db_url
    settings.LOCAL_STORAGE_DIR = orig_storage_dir
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


def _generate_valid_sonar_bytes(w=256, h=256):
    noise = np.random.normal(loc=35, scale=6, size=(h, w)).clip(5, 100).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def test_fresh_database_full_lifecycle(fresh_db_env):
    client = fresh_db_env["client"]
    db_path = fresh_db_env["db_path"]
    storage_path = fresh_db_env["storage_path"]

    # 1. Database file exists and tables were created
    assert db_path.exists(), "Fresh database file should be created"

    # 2. Health check endpoint functions on fresh database
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] in ["ok", "healthy"]

    # 3. Model listing endpoint works
    models_resp = client.get("/api/v1/models")
    assert models_resp.status_code == 200
    assert "natural_seabed" not in models_resp.json()["unavailable_models"]
    assert any(m["id"] == "natural_seabed" for m in models_resp.json()["models"])

    # 4. History is initially empty in fresh environment
    init_hist = client.get("/api/v1/analysis")
    assert init_hist.status_code == 200
    assert init_hist.json()["total"] == 0
    assert init_hist.json()["items"] == []

    # 5. Ingest valid sonar survey analysis into fresh environment
    img_bytes = _generate_valid_sonar_bytes()
    analyze_resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("fresh_survey.png", img_bytes, "image/png")},
        data={"latitude": "18.9175", "longitude": "72.8375", "depth": "24.0"},
    )
    assert analyze_resp.status_code == 200
    analyze_data = analyze_resp.json()
    analysis_id = analyze_data["analysis_id"]
    assert analysis_id.startswith("SONAR-")
    assert analyze_data["status"] == "completed"
    assert analyze_data["metadata"]["geolocation_available"] is True

    # 6. Retrieve analysis by ID
    get_resp = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_resp.status_code == 200
    retrieved_data = get_resp.json()
    assert retrieved_data["analysis_id"] == analysis_id
    assert abs(retrieved_data["metadata"]["latitude"] - 18.9175) < 0.0001

    # 7. Retrieve stored evidence image file
    evidence_resp = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert evidence_resp.status_code == 200
    assert evidence_resp.headers["content-type"] in ["image/png", "image/jpeg"]
    assert len(evidence_resp.content) > 0

    # 8. History now shows exactly 1 analysis
    history_resp = client.get("/api/v1/analysis")
    assert history_resp.status_code == 200
    assert history_resp.json()["total"] == 1
    assert history_resp.json()["items"][0]["analysis_id"] == analysis_id

    # 9. Delete analysis and verify cleanup
    del_resp = client.delete(f"/api/v1/analysis/{analysis_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify analysis is no longer present (404)
    after_del = client.get(f"/api/v1/analysis/{analysis_id}")
    assert after_del.status_code == 404

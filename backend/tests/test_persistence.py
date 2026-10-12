"""Tests for Side-Scan Sonar Persistence and Evidence Storage layer."""

import io
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.db_models import AnalysisRecord, DetectionRecord, EvidenceRecord
from app.repositories.analysis_repository import AnalysisRepository
from app.schemas.analysis import (
    AnalysisBoundingBox,
    AnalysisDetection,
    AnalysisGeolocation,
    AnalysisImageMetadata,
    AnalysisResponse,
    AnalysisSummary,
)
from app.services.analysis_persistence_service import (
    AnalysisPersistenceService,
    PersistenceError,
)
from app.services.storage_service import LocalStorageProvider, StorageError, StorageService

client = TestClient(app)
client.post("/api/v1/session")


def _make_dummy_image_bytes(size=(100, 100), color=(10, 20, 30)) -> bytes:
    """Generate dummy PNG image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


@pytest.fixture
def in_memory_db():
    """Create a fresh isolated in-memory SQLite database session for unit testing."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_storage(tmp_path):
    """Create an isolated LocalStorageProvider in a temporary directory."""
    provider = LocalStorageProvider(base_dir=str(tmp_path))
    return StorageService(provider=provider)


# =========================================================================
# 1. Create Analysis Record & Unit Persistence
# =========================================================================

def test_create_analysis_record(in_memory_db, temp_storage):
    """Test 1: Create and verify analysis record in database."""
    repo = AnalysisRepository(in_memory_db)
    analysis_data = {
        "analysis_id": "test-uuid-001",
        "status": "completed",
        "original_filename": "sonar_ping.png",
        "image_width": 640,
        "image_height": 640,
        "image_channels": 3,
        "image_format": "PNG",
        "image_size_bytes": 1024,
        "total_detections": 0,
        "highest_confidence": 0.0,
        "average_confidence": 0.0,
        "models_executed": ["ghostvision"],
        "objects_by_type": {},
        "execution_time_ms": 12.5,
    }
    evidence_data = {
        "original_filename": "sonar_ping.png",
        "content_type": "image/png",
        "size_bytes": 1024,
        "storage_path": "sonar-evidence/test-uuid-001/original/sonar_ping.png",
        "storage_provider": "local",
    }
    record = repo.create_analysis(analysis_data, [], evidence_data)
    assert record.id is not None
    assert record.analysis_id == "test-uuid-001"
    assert record.status == "completed"
    assert record.original_filename == "sonar_ping.png"


# =========================================================================
# 2. Persist Geolocation
# =========================================================================

def test_persist_geolocation(in_memory_db, temp_storage):
    """Test 2: Ensure navigation and telemetry coordinates persist accurately."""
    repo = AnalysisRepository(in_memory_db)
    analysis_data = {
        "analysis_id": "test-geo-001",
        "status": "completed",
        "original_filename": "survey.png",
        "image_width": 800,
        "image_height": 600,
        "image_channels": 3,
        "latitude": 18.9220,
        "longitude": 72.8347,
        "depth_m": 42.5,
        "heading": 135.0,
        "timestamp": "2026-09-30T10:00:00Z",
        "total_detections": 0,
        "highest_confidence": 0.0,
        "average_confidence": 0.0,
        "models_executed": [],
        "objects_by_type": {},
        "execution_time_ms": 5.0,
    }
    evidence_data = {
        "original_filename": "survey.png",
        "content_type": "image/png",
        "size_bytes": 500,
        "storage_path": "sonar-evidence/test-geo-001/original/survey.png",
        "storage_provider": "local",
    }
    record = repo.create_analysis(analysis_data, [], evidence_data)

    retrieved = repo.get_by_analysis_id("test-geo-001")
    assert retrieved is not None
    assert retrieved.latitude == 18.9220
    assert retrieved.longitude == 72.8347
    assert retrieved.depth_m == 42.5
    assert retrieved.heading == 135.0
    assert retrieved.timestamp == "2026-09-30T10:00:00Z"


# =========================================================================
# 3. Persist Detections
# =========================================================================

def test_persist_detections(in_memory_db, temp_storage):
    """Test 3: Ensure detections with bounding boxes link to parent analysis."""
    repo = AnalysisRepository(in_memory_db)
    analysis_data = {
        "analysis_id": "test-det-001",
        "status": "completed",
        "original_filename": "mine_field.png",
        "image_width": 1000,
        "image_height": 500,
        "image_channels": 3,
        "total_detections": 2,
        "highest_confidence": 0.95,
        "average_confidence": 0.88,
        "models_executed": ["mines"],
        "objects_by_type": {"Mine-Like Contact": 2},
        "execution_time_ms": 30.0,
    }
    detections_data = [
        {
            "detection_id": "DET-01",
            "model": "mines",
            "class_id": 0,
            "raw_class": "MILCO",
            "display_class": "Mine-Like Contact",
            "confidence": 0.95,
            "x1": 100.0,
            "y1": 50.0,
            "x2": 200.0,
            "y2": 150.0,
            "width": 100.0,
            "height": 100.0,
            "norm_x1": 0.1,
            "norm_y1": 0.1,
            "norm_w": 0.1,
            "norm_h": 0.2,
        },
        {
            "detection_id": "DET-02",
            "model": "mines",
            "class_id": 0,
            "raw_class": "MILCO",
            "display_class": "Mine-Like Contact",
            "confidence": 0.81,
            "x1": 300.0,
            "y1": 150.0,
            "x2": 400.0,
            "y2": 250.0,
            "width": 100.0,
            "height": 100.0,
            "norm_x1": 0.3,
            "norm_y1": 0.3,
            "norm_w": 0.1,
            "norm_h": 0.2,
        },
    ]
    evidence_data = {
        "original_filename": "mine_field.png",
        "content_type": "image/png",
        "size_bytes": 2048,
        "storage_path": "sonar-evidence/test-det-001/original/mine_field.png",
        "storage_provider": "local",
    }
    repo.create_analysis(analysis_data, detections_data, evidence_data)

    retrieved = repo.get_by_analysis_id("test-det-001")
    assert retrieved is not None
    assert len(retrieved.detections) == 2
    assert retrieved.detections[0].detection_id == "DET-01"
    assert retrieved.detections[0].display_class == "Mine-Like Contact"
    assert retrieved.detections[1].confidence == 0.81


# =========================================================================
# 4. Persist Summary
# =========================================================================

def test_persist_summary(in_memory_db, temp_storage):
    """Test 4: Statistical summary metrics are persisted accurately."""
    repo = AnalysisRepository(in_memory_db)
    analysis_data = {
        "analysis_id": "test-sum-001",
        "status": "completed",
        "original_filename": "scan.png",
        "image_width": 640,
        "image_height": 640,
        "image_channels": 3,
        "total_detections": 3,
        "highest_confidence": 0.94,
        "average_confidence": 0.82,
        "models_executed": ["ghostvision", "pipeline"],
        "objects_by_type": {"Ghost Gear": 1, "Subsea Pipeline": 2},
        "execution_time_ms": 45.2,
    }
    evidence_data = {
        "original_filename": "scan.png",
        "content_type": "image/png",
        "size_bytes": 1000,
        "storage_path": "sonar-evidence/test-sum-001/original/scan.png",
        "storage_provider": "local",
    }
    repo.create_analysis(analysis_data, [], evidence_data)

    retrieved = repo.get_by_analysis_id("test-sum-001")
    assert retrieved.total_detections == 3
    assert retrieved.highest_confidence == 0.94
    assert retrieved.average_confidence == 0.82
    assert retrieved.objects_by_type == {"Ghost Gear": 1, "Subsea Pipeline": 2}
    assert retrieved.models_executed == ["ghostvision", "pipeline"]


# =========================================================================
# 5. Retrieve Analysis by analysis_id
# =========================================================================

def test_retrieve_analysis_by_id(in_memory_db, temp_storage):
    """Test 5: Retrieve complete analysis detail via persistence service."""
    service = AnalysisPersistenceService(storage=temp_storage)

    mock_resp = AnalysisResponse(
        analysis_id="retrieve-test-123",
        status="completed",
        image=AnalysisImageMetadata(filename="ret_test.png", width=640, height=640, channels=3, size_bytes=512),
        geolocation=AnalysisGeolocation(latitude=12.34, longitude=56.78, depth_m=10.0, heading=90.0),
        detections=[
            AnalysisDetection(
                id="DET-01",
                model="ghostvision",
                class_id=0,
                raw_class="Crab-Pot",
                display_class="Ghost Gear",
                confidence=0.88,
                bbox=AnalysisBoundingBox(x1=10, y1=20, x2=50, y2=60, width=40, height=40, norm_x1=0.1, norm_y1=0.2, norm_w=0.4, norm_h=0.4),
            )
        ],
        summary=AnalysisSummary(
            total_detections=1,
            objects_by_type={"Ghost Gear": 1},
            highest_confidence=0.88,
            average_confidence=0.88,
            models_executed=["ghostvision"],
            execution_time_ms=15.0,
        ),
    )

    img_data = _make_dummy_image_bytes()
    service.persist_analysis(mock_resp, img_data, "image/png", in_memory_db)

    detail = service.get_analysis_by_id("retrieve-test-123", in_memory_db)
    assert detail is not None
    assert detail.analysis_id == "retrieve-test-123"
    assert detail.geolocation.latitude == 12.34
    assert len(detail.detections) == 1
    assert detail.evidence is not None
    assert detail.evidence.original_filename == "ret_test.png"
    assert detail.evidence.access_url == "/api/v1/analysis/retrieve-test-123/evidence"


# =========================================================================
# 6. List Analyses & 7. Pagination
# =========================================================================

def test_list_analyses_and_pagination(in_memory_db, temp_storage):
    """Tests 6 & 7: Test list querying, pagination boundaries, and page count."""
    service = AnalysisPersistenceService(storage=temp_storage)
    img_data = _make_dummy_image_bytes()

    # Seed 5 analyses
    for i in range(5):
        resp = AnalysisResponse(
            analysis_id=f"page-test-{i:03d}",
            status="completed",
            image=AnalysisImageMetadata(filename=f"scan_{i}.png", width=640, height=640),
            geolocation=AnalysisGeolocation(),
            detections=[],
            summary=AnalysisSummary(total_detections=0, objects_by_type={}, highest_confidence=0.0, average_confidence=0.0),
        )
        service.persist_analysis(resp, img_data, "image/png", in_memory_db)

    # Page 1 with page_size=2
    page1 = service.list_analyses(page=1, page_size=2, status=None, detection_type=None, db=in_memory_db)
    assert page1.total == 5
    assert page1.page == 1
    assert page1.page_size == 2
    assert page1.total_pages == 3
    assert len(page1.items) == 2

    # Page 3 with page_size=2
    page3 = service.list_analyses(page=3, page_size=2, status=None, detection_type=None, db=in_memory_db)
    assert len(page3.items) == 1


# =========================================================================
# 8. Empty Detection Analysis
# =========================================================================

def test_empty_detection_analysis(in_memory_db, temp_storage):
    """Test 8: Ensure analysis with 0 detections persists cleanly."""
    service = AnalysisPersistenceService(storage=temp_storage)
    img_data = _make_dummy_image_bytes()

    resp = AnalysisResponse(
        analysis_id="empty-det-001",
        status="completed",
        image=AnalysisImageMetadata(filename="empty.png", width=500, height=500),
        geolocation=AnalysisGeolocation(),
        detections=[],
        summary=AnalysisSummary(total_detections=0, objects_by_type={}, highest_confidence=0.0, average_confidence=0.0),
    )
    service.persist_analysis(resp, img_data, "image/png", in_memory_db)

    record = service.get_analysis_by_id("empty-det-001", in_memory_db)
    assert record is not None
    assert record.summary.total_detections == 0
    assert len(record.detections) == 0


# =========================================================================
# 9, 10, 11. Coordinate Range Validations (API Layer)
# =========================================================================

def test_invalid_latitude():
    """Test 9: Latitude outside [-90, 90] returns 400 Bad Request."""
    img_bytes = _make_dummy_image_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"latitude": 95.0}  # Invalid (>90)
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Latitude must be between -90.0 and 90.0" in response.json()["detail"]


def test_invalid_longitude():
    """Test 10: Longitude outside [-180, 180] returns 400 Bad Request."""
    img_bytes = _make_dummy_image_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"longitude": -195.0}  # Invalid (<-180)
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Longitude must be between -180.0 and 180.0" in response.json()["detail"]


def test_invalid_heading():
    """Test 11: Heading outside [0, 360] returns 400 Bad Request."""
    img_bytes = _make_dummy_image_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"heading": 361.0}  # Invalid (>360)
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Heading must be between 0.0 and 360.0" in response.json()["detail"]


# =========================================================================
# 12. Evidence Metadata & File Retrieval
# =========================================================================

def test_evidence_metadata_and_retrieval(in_memory_db, temp_storage):
    """Test 12: Evidence metadata recorded and file served correctly."""
    service = AnalysisPersistenceService(storage=temp_storage)
    img_data = _make_dummy_image_bytes(size=(64, 64))

    resp = AnalysisResponse(
        analysis_id="evidence-test-01",
        status="completed",
        image=AnalysisImageMetadata(filename="sample_sonar.png", width=64, height=64),
        geolocation=AnalysisGeolocation(),
        detections=[],
        summary=AnalysisSummary(total_detections=0, objects_by_type={}, highest_confidence=0.0, average_confidence=0.0),
    )
    service.persist_analysis(resp, img_data, "image/png", in_memory_db)

    file_bytes, content_type, filename = service.get_evidence_file("evidence-test-01", in_memory_db)
    assert file_bytes == img_data
    assert content_type == "image/png"
    assert filename == "sample_sonar.png"


# =========================================================================
# 13. Storage Failure Handling
# =========================================================================

def test_storage_failure_handling(in_memory_db):
    """Test 13: When storage write fails, PersistenceError is raised cleanly."""
    mock_storage = MagicMock()
    mock_storage.save_evidence.side_effect = StorageError("Disk full or bucket unreachable")

    service = AnalysisPersistenceService(storage=mock_storage)
    resp = AnalysisResponse(
        analysis_id="fail-storage-01",
        status="completed",
        image=AnalysisImageMetadata(filename="sample.png", width=10, height=10),
        geolocation=AnalysisGeolocation(),
        detections=[],
        summary=AnalysisSummary(total_detections=0, objects_by_type={}, highest_confidence=0.0, average_confidence=0.0),
    )

    with pytest.raises(PersistenceError) as exc_info:
        service.persist_analysis(resp, b"fake-bytes", "image/png", in_memory_db)
    assert "Evidence image storage failed" in str(exc_info.value)


# =========================================================================
# 14. Database Failure Handling & Evidence Cleanup
# =========================================================================

def test_database_failure_handling_cleans_up_evidence(in_memory_db, temp_storage):
    """Test 14: If DB write fails, uploaded evidence file is deleted so no orphan is left."""
    service = AnalysisPersistenceService(storage=temp_storage)
    img_data = _make_dummy_image_bytes()

    resp = AnalysisResponse(
        analysis_id="fail-db-01",
        status="completed",
        image=AnalysisImageMetadata(filename="clean_test.png", width=10, height=10),
        geolocation=AnalysisGeolocation(),
        detections=[],
        summary=AnalysisSummary(total_detections=0, objects_by_type={}, highest_confidence=0.0, average_confidence=0.0),
    )

    # Force a DB error by patching AnalysisRepository.create_analysis
    with patch.object(AnalysisRepository, "create_analysis", side_effect=Exception("DB constraint violation")):
        with pytest.raises(PersistenceError):
            service.persist_analysis(resp, img_data, "image/png", in_memory_db)

    # Verify evidence was not left orphaned in storage
    storage_path = temp_storage.build_storage_path("fail-db-01", "clean_test.png")
    assert not temp_storage.provider.file_exists(storage_path)


# =========================================================================
# 15. Full POST /analysis/analyze Persistence Flow & Regression
# =========================================================================

def test_full_analysis_analyze_persistence_flow():
    """Test 15: End-to-end POST /analyze saves DB record, evidence, and returns compliant JSON."""
    img_bytes = _make_dummy_image_bytes(size=(640, 640))
    files = {"image": ("survey_run_e2e.png", img_bytes, "image/png")}
    data = {
        "selected_models": "ghostvision",
        "latitude": 15.2993,
        "longitude": 74.1240,
        "depth": 35.0,
        "heading": 270.0,
    }

    # Mock the internal inference engine so unit test is fast and doesn't load model on disk
    mock_inference_resp = MagicMock(
        model_name="ghostvision",
        detections=[],
        inference_time_ms=10.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_inference_resp):
        response = client.post("/api/v1/analysis/analyze", files=files, data=data)

    assert response.status_code == 200
    json_data = response.json()
    assert "analysis_id" in json_data
    analysis_id = json_data["analysis_id"]
    assert json_data["status"] == "completed"
    assert json_data["geolocation"]["latitude"] == 15.2993
    assert json_data["geolocation"]["longitude"] == 74.1240
    assert json_data["geolocation"]["heading"] == 270.0

    # Verify GET /api/v1/analysis/{analysis_id} retrieves persisted data
    get_res = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["analysis_id"] == analysis_id
    assert detail["evidence"]["original_filename"] == "survey_run_e2e.png"

    # Verify GET /api/v1/analysis/{analysis_id}/evidence serves original image
    evidence_res = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert evidence_res.status_code == 200
    assert evidence_res.content == img_bytes

    # Verify GET /api/v1/analysis lists this item
    list_res = client.get("/api/v1/analysis?page=1&page_size=10")
    assert list_res.status_code == 200
    list_json = list_res.json()
    assert list_json["total"] >= 1
    found_ids = [item["analysis_id"] for item in list_json["items"]]
    assert analysis_id in found_ids

    # Verify DELETE /api/v1/analysis/{analysis_id} deletes it
    del_res = client.delete(f"/api/v1/analysis/{analysis_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify it is no longer retrievable
    del_check = client.get(f"/api/v1/analysis/{analysis_id}")
    assert del_check.status_code == 404

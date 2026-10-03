"""Unit and API tests for the Side-Scan Sonar Analysis Pipeline."""

import io
from unittest.mock import patch
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisGeolocation
from app.schemas.inference import BoundingBox, DetectionResult, InferenceResponse
from app.services.analysis_service import (
    ModelUnavailableError,
    analysis_service,
    resolve_analysis_models,
)
from app.services.detection_normalizer import (
    compute_analysis_summary,
    normalize_class_name,
)
from app.services.preprocessing_service import (
    ImageValidationError,
    UnsupportedFormatError,
    preprocess_image_bytes,
)

client = TestClient(app)


def _create_image_bytes(format_name: str = "PNG", size=(640, 640), color=(15, 25, 35)) -> bytes:
    """Helper to generate in-memory valid image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format_name)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------
# 1. Preprocessing Service Unit Tests
# ---------------------------------------------------------

def test_preprocess_valid_png():
    """Verify preprocessing of standard PNG bytes."""
    raw_bytes = _create_image_bytes("PNG", size=(800, 600))
    pre = preprocess_image_bytes(raw_bytes, "sonar_01.png", "image/png")
    assert pre.width == 800
    assert pre.height == 600
    assert pre.channels == 3
    assert pre.format == "PNG"
    assert pre.np_array.shape == (600, 800, 3)


def test_preprocess_valid_tiff():
    """Verify preprocessing of TIFF bytes."""
    raw_bytes = _create_image_bytes("TIFF", size=(640, 480))
    pre = preprocess_image_bytes(raw_bytes, "swath.tif", "image/tiff")
    assert pre.width == 640
    assert pre.height == 480
    assert pre.channels == 3


def test_preprocess_empty_bytes_fails():
    """Verify rejection of 0-byte file."""
    with pytest.raises(ImageValidationError):
        preprocess_image_bytes(b"", "empty.png", "image/png")


def test_preprocess_unsupported_format_fails():
    """Verify rejection of unsupported format extension and MIME."""
    with pytest.raises(UnsupportedFormatError):
        preprocess_image_bytes(b"some-text", "notes.pdf", "application/pdf")


def test_preprocess_corrupted_image_fails():
    """Verify rejection of non-image payload."""
    with pytest.raises(ImageValidationError):
        preprocess_image_bytes(b"NOT_A_VALID_IMAGE_HEADER", "bad.jpg", "image/jpeg")


# ---------------------------------------------------------
# 2. Semantic Class Normalization Unit Tests
# ---------------------------------------------------------

def test_semantic_class_mappings_exact():
    """Verify strict class normalization mappings required by project."""
    assert normalize_class_name("Crab-Pot") == "Ghost Gear"
    assert normalize_class_name("Pipeline") == "Subsea Pipeline"
    assert normalize_class_name("Cylinder") == "Cylinder"
    assert normalize_class_name("Shipwreck") == "Shipwreck"
    assert normalize_class_name("MILCO") == "Mine-Like Contact"
    assert normalize_class_name("NOMBO") == "Non-Mine Mine-Like Bottom Object"
    assert normalize_class_name("Class_0") == "Class_0 (Unknown / Unlabeled)"


def test_summary_calculation():
    """Verify summary calculations with empty and populated detections."""
    empty_sum = compute_analysis_summary([], ["ghostvision"], 12.5)
    assert empty_sum.total_detections == 0
    assert empty_sum.highest_confidence == 0.0
    assert empty_sum.average_confidence == 0.0
    assert empty_sum.objects_by_type == {}
    assert empty_sum.execution_time_ms == 12.5


# ---------------------------------------------------------
# 3. Model Resolution & Selection Tests
# ---------------------------------------------------------

def test_resolve_models_all_default():
    """Verify default model resolution selects all 5 verified models."""
    resolved = resolve_analysis_models(None)
    keys = [m.key for m in resolved]
    assert keys == ["cylinder", "ghostvision", "mines", "shipwreck", "subpipes"]


def test_resolve_models_selected_subset():
    """Verify subset selection with aliases."""
    resolved = resolve_analysis_models(["ghostvision", "pipeline", "mine"])
    keys = [m.key for m in resolved]
    assert keys == ["ghostvision", "subpipes", "mines"]


def test_resolve_models_natural_seabed_accepted():
    """Verify requesting natural_seabed resolves correctly."""
    resolved = resolve_analysis_models(["natural_seabed"])
    assert len(resolved) == 1
    assert resolved[0].key == "natural_seabed"
    assert resolved[0].task == "classify"


# ---------------------------------------------------------
# 4. End-to-End Pipeline Service Unit Tests
# ---------------------------------------------------------

def test_analysis_service_real_selected_model():
    """Verify real pipeline execution on selected model."""
    img_bytes = _create_image_bytes("PNG", size=(640, 640))
    res = analysis_service.analyze_sonar_image(
        file_bytes=img_bytes,
        filename="test.png",
        selected_models=["ghostvision"],
    )
    assert res.status == "completed"
    assert res.analysis_id.startswith("SONAR-")
    assert res.image.width == 640
    assert res.image.height == 640
    assert "ghostvision" in res.summary.models_executed
    assert res.geolocation.latitude is None


def test_analysis_service_preserves_geolocation():
    """Verify geolocation telemetry is preserved exactly without fabrication."""
    img_bytes = _create_image_bytes("PNG", size=(640, 640))
    geo = AnalysisGeolocation(
        latitude=18.9169,
        longitude=72.8365,
        depth_m=45.2,
        heading=135.0,
        timestamp="2026-09-30T00:00:00Z",
    )
    res = analysis_service.analyze_sonar_image(
        file_bytes=img_bytes,
        filename="survey.png",
        selected_models=["ghostvision"],
        geolocation=geo,
    )
    assert res.geolocation.latitude == 18.9169
    assert res.geolocation.longitude == 72.8365
    assert res.geolocation.depth_m == 45.2
    assert res.geolocation.heading == 135.0
    assert res.geolocation.timestamp == "2026-09-30T00:00:00Z"


# ---------------------------------------------------------
# 5. API Endpoint Tests (POST /api/v1/analysis/analyze)
# ---------------------------------------------------------

def test_api_analyze_success():
    """Verify POST /api/v1/analysis/analyze returns structured response."""
    img_bytes = _create_image_bytes("JPEG", size=(640, 640))
    response = client.post(
        "/api/v1/analysis/analyze",
        data={"selected_models": "ghostvision", "confidence": 0.25},
        files={"image": ("sonar_slice.jpg", img_bytes, "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "analysis_id" in data
    assert data["image"]["filename"] == "sonar_slice.jpg"
    assert data["image"]["width"] == 640
    assert data["image"]["height"] == 640
    assert "detections" in data
    assert "summary" in data
    assert "ghostvision" in data["summary"]["models_executed"]
    assert data["geolocation"]["latitude"] is None


def test_api_analyze_with_geolocation():
    """Verify geolocation parameters are preserved in API response."""
    img_bytes = _create_image_bytes("PNG", size=(640, 640))
    response = client.post(
        "/api/v1/analysis/analyze",
        data={
            "selected_models": "ghostvision",
            "latitude": 18.9184,
            "longitude": 72.8392,
            "depth": 38.5,
            "heading": 270.0,
            "timestamp": "2026-09-30T00:15:30Z",
        },
        files={"image": ("survey_geo.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["geolocation"]["latitude"] == 18.9184
    assert data["geolocation"]["longitude"] == 72.8392
    assert data["geolocation"]["depth_m"] == 38.5
    assert data["geolocation"]["heading"] == 270.0
    assert data["geolocation"]["timestamp"] == "2026-09-30T00:15:30Z"


def test_api_analyze_unsupported_file():
    """Verify rejection of non-image file with HTTP 415."""
    response = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("nav.log", b"RAW LOG DATA", "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported file format" in response.json()["detail"]


def test_api_analyze_corrupted_image():
    """Verify rejection of corrupted image bytes with HTTP 400."""
    response = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("corrupted.png", b"CORRUPTED_STREAM", "image/png")},
    )
    assert response.status_code == 400
    assert "corrupted" in response.json()["detail"].lower()


def test_api_analyze_invalid_heading():
    """Verify rejection of heading outside [0 - 360]."""
    img_bytes = _create_image_bytes("PNG")
    response = client.post(
        "/api/v1/analysis/analyze",
        data={"heading": 420.0},
        files={"image": ("sonar.png", img_bytes, "image/png")},
    )
    assert response.status_code == 400
    assert "Heading must be between" in response.json()["detail"]


def test_api_analyze_natural_seabed_accepted():
    """Verify requesting natural_seabed model executes Stage 1 classification successfully."""
    img_bytes = _create_image_bytes("PNG")
    response = client.post(
        "/api/v1/analysis/analyze",
        data={"selected_models": "natural_seabed"},
        files={"image": ("sonar.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["triage"] is not None
    assert "clean_probability" in data["triage"]
    assert "natural_seabed" in data["summary"]["models_executed"]


def test_api_analyze_mocked_multi_detections():
    """Verify normalized output and category aggregations when detections occur."""
    mock_bbox1 = BoundingBox(
        x1=100.0, y1=150.0, x2=300.0, y2=450.0, width=200.0, height=300.0,
        norm_x1=0.1, norm_y1=0.15, norm_w=0.2, norm_h=0.3
    )
    mock_bbox2 = BoundingBox(
        x1=500.0, y1=200.0, x2=800.0, y2=350.0, width=300.0, height=150.0,
        norm_x1=0.5, norm_y1=0.2, norm_w=0.3, norm_h=0.15
    )

    det1 = DetectionResult(
        model_name="shipwreck",
        class_id=3,
        raw_class_name="Shipwreck",
        semantic_class_name="Maritime Shipwreck / Hull",
        confidence=0.94,
        bounding_box=mock_bbox1,
        image_width=1000,
        image_height=1000,
    )
    det2 = DetectionResult(
        model_name="ghostvision",
        class_id=0,
        raw_class_name="Crab-Pot",
        semantic_class_name="Abandoned Fishing Gear (Crab Pot / Trap)",
        confidence=0.88,
        bounding_box=mock_bbox2,
        image_width=1000,
        image_height=1000,
    )

    resp1 = InferenceResponse(
        model_name="shipwreck", model_architecture="YOLO26n",
        detections_count=1, detections=[det1], image_width=1000, image_height=1000, inference_time_ms=25.0
    )
    resp2 = InferenceResponse(
        model_name="ghostvision", model_architecture="YOLO12s",
        detections_count=1, detections=[det2], image_width=1000, image_height=1000, inference_time_ms=20.0
    )

    def mock_predict(name_or_key, **kwargs):
        if name_or_key == "shipwreck":
            return resp1
        return resp2

    with patch("app.services.analysis_service.inference_service.predict", side_effect=mock_predict):
        img_bytes = _create_image_bytes("PNG", size=(1000, 1000))
        response = client.post(
            "/api/v1/analysis/analyze",
            data={"selected_models": "shipwreck,ghostvision"},
            files={"image": ("survey.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_detections"] == 2
        assert data["summary"]["objects_by_type"] == {
            "Shipwreck": 1,
            "Ghost Gear": 1,
        }
        assert data["summary"]["highest_confidence"] == 0.94
        assert data["summary"]["average_confidence"] == 0.91

        # Check detection items
        d1 = data["detections"][0]
        assert d1["id"] == "DET-01"
        assert d1["raw_class"] == "Shipwreck"
        assert d1["display_class"] == "Shipwreck"

        d2 = data["detections"][1]
        assert d2["id"] == "DET-02"
        assert d2["raw_class"] == "Crab-Pot"
        assert d2["display_class"] == "Ghost Gear"

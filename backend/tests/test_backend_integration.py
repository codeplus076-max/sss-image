"""End-to-end integration and frontend contract verification tests."""

import io
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.inference import BoundingBox, DetectionResult, InferenceResponse

client = TestClient(app)


def _generate_test_image_bytes(format_name: str = "PNG", size=(640, 640), color=(15, 25, 35)) -> bytes:
    """Generate in-memory valid image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format_name)
    buf.seek(0)
    return buf.read()


# =========================================================================
# 1. Successful Multipart Image Upload & Response Structure
# =========================================================================

def test_successful_multipart_image_upload():
    """Verify multipart sonar upload returns 200 and frontend-compatible schema."""
    img_bytes = _generate_test_image_bytes("PNG", size=(800, 600))
    files = {"image": ("sonar_survey_test.png", img_bytes, "image/png")}
    data = {
        "selected_models": "ghostvision",
        "latitude": 18.9220,
        "longitude": 72.8347,
        "depth": 32.5,
        "heading": 115.0,
    }

    mock_resp = InferenceResponse(
        model_name="ghostvision",
        model_architecture="YOLO12s",
        detections_count=1,
        detections=[
            DetectionResult(
                model_name="ghostvision",
                class_id=0,
                raw_class_name="Crab-Pot",
                semantic_class_name="Abandoned Fishing Gear (Crab Pot / Trap)",
                confidence=0.912,
                bounding_box=BoundingBox(
                    x1=100.0,
                    y1=150.0,
                    x2=200.0,
                    y2=250.0,
                    width=100.0,
                    height=100.0,
                    norm_x1=0.125,
                    norm_y1=0.25,
                    norm_w=0.125,
                    norm_h=0.1667,
                ),
                image_width=800,
                image_height=600,
            )
        ],
        image_width=800,
        image_height=600,
        inference_time_ms=12.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_resp):
        response = client.post("/api/v1/analysis/analyze", files=files, data=data)

    assert response.status_code == 200
    res_json = response.json()

    # Core structure
    assert "analysis_id" in res_json
    assert res_json["analysis_id"].startswith("SONAR-")
    assert res_json["status"] == "completed"
    assert res_json["image"]["filename"] == "sonar_survey_test.png"
    assert res_json["image"]["width"] == 800
    assert res_json["image"]["height"] == 600
    assert res_json["evidence_url"] == f"/api/v1/analysis/{res_json['analysis_id']}/evidence"

    # Geolocation
    assert res_json["geolocation"]["latitude"] == 18.9220
    assert res_json["geolocation"]["longitude"] == 72.8347
    assert res_json["geolocation"]["depth_m"] == 32.5
    assert res_json["geolocation"]["heading"] == 115.0

    # Detection & frontend bindings
    assert len(res_json["detections"]) == 1
    det = res_json["detections"][0]
    assert det["id"] == "DET-01"
    assert det["code"] == "01"
    assert det["className"] == "GHOST GEAR"
    assert det["display_class"] == "Ghost Gear"
    assert det["status"] == "PENDING REVIEW"
    assert det["confidence"] == 0.912
    assert det["confidence_percent"] == 91.2
    assert det["geoLat"] == 18.9220
    assert det["geoLon"] == 72.8347
    assert det["bbox"]["x"] == 12.5  # norm_x1 * 100
    assert det["bbox"]["y"] == 25.0  # norm_y1 * 100
    assert det["bbox"]["w"] == 12.5  # norm_w * 100
    assert det["bbox"]["h"] == 16.67 # norm_h * 100
    assert det["imagePosition"]["display"] == "X: 12%, Y: 25%"

    # Summary
    assert res_json["summary"]["total_detections"] == 1
    assert res_json["summary"]["objects_by_type"] == {"Ghost Gear": 1}
    assert res_json["summary"]["highest_confidence"] == 0.912


# =========================================================================
# 2. Selected Model Validation & Aliases
# =========================================================================

def test_selected_model_validation_and_aliases():
    """Verify model selection accepts canonical names, aliases, and comma-separated strings."""
    img_bytes = _generate_test_image_bytes()
    mock_resp = InferenceResponse(
        model_name="subpipes",
        model_architecture="YOLO12s",
        detections_count=0,
        detections=[],
        image_width=640,
        image_height=640,
        inference_time_ms=5.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_resp):
        # Test alias 'pipeline'
        res = client.post(
            "/api/v1/analysis/analyze",
            files={"image": ("test.png", img_bytes, "image/png")},
            data={"selected_models": "pipeline"},
        )
        assert res.status_code == 200
        assert "subpipes" in res.json()["summary"]["models_executed"]

        # Test alias 'mine'
        res2 = client.post(
            "/api/v1/analysis/analyze",
            files={"image": ("test.png", img_bytes, "image/png")},
            data={"selected_models": "mine"},
        )
        assert res2.status_code == 200
        assert "mines" in res2.json()["summary"]["models_executed"]


# =========================================================================
# 3. Invalid Model Handling & Verified Natural Seabed Execution
# =========================================================================

def test_invalid_model_handling():
    """Verify requesting an unknown model returns 400 Bad Request."""
    img_bytes = _generate_test_image_bytes()
    res = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("test.png", img_bytes, "image/png")},
        data={"selected_models": "non_existent_laser_model"},
    )
    assert res.status_code == 400
    assert "is not registered" in res.json()["detail"]


def test_natural_seabed_model_available():
    """Verify requesting Natural Seabed executes classification triage successfully."""
    img_bytes = _generate_test_image_bytes()
    res = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("test.png", img_bytes, "image/png")},
        data={"selected_models": "natural_seabed"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["triage"] is not None
    assert "clean_probability" in data["triage"]
    assert "natural_seabed" in data["summary"]["models_executed"]


# =========================================================================
# 4. Geolocation Validation
# =========================================================================

def test_geolocation_bounds_validation():
    """Verify latitude [-90, 90], longitude [-180, 180], heading [0, 360]."""
    img_bytes = _generate_test_image_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}

    # Lat < -90
    r = client.post("/api/v1/analysis/analyze", files=files, data={"latitude": -91.0})
    assert r.status_code == 400
    assert "Latitude must be between" in r.json()["detail"]

    # Lon > 180
    r = client.post("/api/v1/analysis/analyze", files=files, data={"longitude": 185.0})
    assert r.status_code == 400
    assert "Longitude must be between" in r.json()["detail"]

    # Heading < 0
    r = client.post("/api/v1/analysis/analyze", files=files, data={"heading": -5.0})
    assert r.status_code == 400
    assert "Heading must be between" in r.json()["detail"]


# =========================================================================
# 5. Multi-Model Inference Execution
# =========================================================================

def test_multi_model_inference_execution():
    """Verify running multiple specified models in a single analysis request."""
    img_bytes = _generate_test_image_bytes()
    mock_resp = InferenceResponse(
        model_name="mock",
        model_architecture="mock",
        detections_count=0,
        detections=[],
        image_width=640,
        image_height=640,
        inference_time_ms=5.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_resp):
        res = client.post(
            "/api/v1/analysis/analyze",
            files={"image": ("survey.png", img_bytes, "image/png")},
            data={"selected_models": "cylinder,mines,shipwreck"},
        )
    assert res.status_code == 200
    models_run = res.json()["summary"]["models_executed"]
    assert "cylinder" in models_run
    assert "mines" in models_run
    assert "shipwreck" in models_run


# =========================================================================
# 6. Persisted Analysis & Evidence Retrieval
# =========================================================================

def test_persisted_analysis_and_evidence_retrieval():
    """Verify complete persistence, retrieval by ID, and streaming of evidence."""
    img_bytes = _generate_test_image_bytes("JPEG", size=(320, 240))
    files = {"image": ("deep_survey.jpg", img_bytes, "image/jpeg")}

    mock_resp = InferenceResponse(
        model_name="mines",
        model_architecture="YOLO12s",
        detections_count=0,
        detections=[],
        image_width=320,
        image_height=240,
        inference_time_ms=8.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_resp):
        post_res = client.post("/api/v1/analysis/analyze", files=files, data={"selected_models": "mines"})

    assert post_res.status_code == 200
    analysis_id = post_res.json()["analysis_id"]

    # 1. Retrieve by analysis_id
    get_res = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["analysis_id"] == analysis_id
    assert detail["evidence"]["original_filename"] == "deep_survey.jpg"
    assert detail["evidence"]["content_type"] == "image/jpeg"

    # 2. Retrieve evidence file
    evidence_res = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert evidence_res.status_code == 200
    assert evidence_res.content == img_bytes


# =========================================================================
# 7. Invalid Image Handling
# =========================================================================

def test_invalid_image_handling():
    """Verify non-image content or corrupted bytes are cleanly rejected."""
    corrupted_bytes = b"NOT_A_VALID_SONAR_IMAGE_PAYLOAD"
    files = {"image": ("corrupted.png", corrupted_bytes, "image/png")}
    res = client.post("/api/v1/analysis/analyze", files=files)
    assert res.status_code in (400, 415)

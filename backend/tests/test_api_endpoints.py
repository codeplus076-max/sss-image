"""API endpoint integration and validation tests."""

import io
from unittest.mock import patch
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.inference import BoundingBox, DetectionResult, InferenceResponse

client = TestClient(app)


def _create_test_image_bytes(format_name: str = "PNG", size=(640, 640), color=(10, 20, 30)) -> bytes:
    """Helper to generate in-memory valid image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format_name)
    buf.seek(0)
    return buf.read()


# 1. Health API Test
def test_api_health_endpoint():
    """Verify GET /api/v1/health returns 200 with service and model availability."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "sonar-backend"
    models = data["models"]
    assert models["cylinder"] == "available"
    assert models["ghostvision"] == "available"
    assert models["mine"] == "available"
    assert models["shipwreck"] == "available"
    assert models["subpipe"] == "available"
    assert models["natural_seabed"] == "available"


# 2. Models Listing API Test
def test_api_models_endpoint():
    """Verify GET /api/v1/models returns all registered models with raw and semantic class mappings."""
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert data["total"] == 6

    models_by_id = {m["id"]: m for m in data["models"]}
    assert "cylinder" in models_by_id
    assert "ghostvision" in models_by_id
    assert "mines" in models_by_id
    assert "shipwreck" in models_by_id
    assert "subpipes" in models_by_id
    assert "natural_seabed" in models_by_id

    # Verify Cylinder input resolution
    assert models_by_id["cylinder"]["input_resolution"] == [1536, 1536]

    # Verify Shipwreck class mappings
    shipwreck_classes = {c["class_id"]: c for c in models_by_id["shipwreck"]["class_mappings"]}
    assert 0 in shipwreck_classes
    assert "shipwreck" in shipwreck_classes[0]["raw_class_name"].lower()
    assert "Shipwreck" in shipwreck_classes[0]["display_name"] or "Hull" in shipwreck_classes[0]["display_name"]

    # Verify Natural Seabed is active and not in unavailable_models
    assert "unavailable_models" in data
    assert "natural_seabed" not in data["unavailable_models"]
    assert models_by_id["natural_seabed"]["status"] == "available"
    assert models_by_id["natural_seabed"]["task"] == "classify"


# 3. Real Integration Test (Reaching Actual Model Inference Service)
def test_api_predict_real_inference_ghostvision():
    """Verify POST /api/v1/inference/predict executes real inference and returns normalized schema."""
    img_bytes = _create_test_image_bytes("JPEG", size=(640, 640))
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision", "confidence": 0.25, "iou": 0.70},
        files={"image": ("sonar_test.jpg", img_bytes, "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["model"]["id"] == "ghostvision"
    assert data["image"]["width"] == 640
    assert data["image"]["height"] == 640
    assert isinstance(data["detections"], list)
    assert data["count"] == len(data["detections"])


# 4. Missing Image Validation
def test_api_predict_missing_image():
    """Verify rejection when image file is missing from multipart payload."""
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision"},
    )
    assert response.status_code in (400, 422)


# 5. Unsupported Image Format Validation
def test_api_predict_unsupported_image():
    """Verify rejection when unsupported media type is uploaded."""
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision"},
        files={"image": ("document.txt", b"This is not a sonar image.", "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported image format" in response.json()["detail"]


# 6. Empty Image Data Validation
def test_api_predict_empty_image():
    """Verify rejection when uploaded file is zero bytes."""
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision"},
        files={"image": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


# 7. Corrupted Image Validation
def test_api_predict_corrupted_image():
    """Verify rejection when image bytes cannot be decoded."""
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision"},
        files={"image": ("corrupted.png", b"CORRUPTED_BYTES_HERE", "image/png")},
    )
    assert response.status_code == 400
    assert "corrupted" in response.json()["detail"].lower()


# 8. Unknown Model Validation
def test_api_predict_unknown_model():
    """Verify rejection when model identifier is unrecognized."""
    img_bytes = _create_test_image_bytes("PNG")
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "non_existent_sonar_model"},
        files={"image": ("test.png", img_bytes, "image/png")},
    )
    assert response.status_code == 400
    assert "Unknown model" in response.json()["detail"]


# 9. Invalid Confidence Threshold Validation
def test_api_predict_invalid_confidence():
    """Verify rejection when confidence is outside [0.0 - 1.0]."""
    img_bytes = _create_test_image_bytes("PNG")
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision", "confidence": 1.5},
        files={"image": ("test.png", img_bytes, "image/png")},
    )
    assert response.status_code == 400
    assert "Confidence threshold must be between 0.0 and 1.0" in response.json()["detail"]


# 10. Invalid IoU Threshold Validation
def test_api_predict_invalid_iou():
    """Verify rejection when IoU is outside [0.0 - 1.0]."""
    img_bytes = _create_test_image_bytes("PNG")
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "ghostvision", "iou": -0.1},
        files={"image": ("test.png", img_bytes, "image/png")},
    )
    assert response.status_code == 400
    assert "IoU threshold must be between 0.0 and 1.0" in response.json()["detail"]


# 11. Normalized Detection Response (Mocked Detection Pipeline)
def test_api_predict_normalized_detections_response():
    """Verify normalized output structure when detections are present."""
    mock_bbox = BoundingBox(
        x1=120.0,
        y1=240.0,
        x2=580.0,
        y2=620.0,
        width=460.0,
        height=380.0,
        norm_x1=0.0625,
        norm_y1=0.2222,
        norm_w=0.2396,
        norm_h=0.3519,
    )
    mock_detection = DetectionResult(
        model_name="shipwreck",
        class_id=3,
        raw_class_name="Shipwreck",
        semantic_class_name="Maritime Shipwreck / Hull",
        confidence=0.91,
        bounding_box=mock_bbox,
        image_width=1920,
        image_height=1080,
    )
    mock_response = InferenceResponse(
        model_name="shipwreck",
        model_architecture="YOLO26n",
        detections_count=1,
        detections=[mock_detection],
        image_width=1920,
        image_height=1080,
        inference_time_ms=45.2,
    )

    with patch("app.api.v1.routes.inference.inference_service.predict", return_value=mock_response):
        img_bytes = _create_test_image_bytes("PNG", size=(1920, 1080))
        response = client.post(
            "/api/v1/inference/predict",
            data={"model": "shipwreck", "confidence": 0.50},
            files={"image": ("survey_swath.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["model"]["id"] == "shipwreck"
        assert data["model"]["name"] == "Shipwreck Detector"
        assert data["image"]["width"] == 1920
        assert data["image"]["height"] == 1080

        det = data["detections"][0]
        assert det["class_id"] == 3
        assert det["raw_class_name"] == "Shipwreck"
        assert det["display_name"] == "Maritime Shipwreck / Hull"
        assert det["confidence"] == 0.91
        assert det["bounding_box"]["x1"] == 120.0
        assert det["bounding_box"]["y1"] == 240.0
        assert det["bounding_box"]["x2"] == 580.0
        assert det["bounding_box"]["y2"] == 620.0


# 12. Model Alias Resolution (mine -> mines, subpipe -> subpipes)
def test_api_predict_model_alias():
    """Verify singular aliases 'mine' and 'subpipe' resolve seamlessly."""
    img_bytes = _create_test_image_bytes("PNG", size=(640, 640))
    response = client.post(
        "/api/v1/inference/predict",
        data={"model": "mine"},
        files={"image": ("test.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["model"]["id"] == "mines"

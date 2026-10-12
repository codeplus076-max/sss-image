"""Tests for Sonar Image Gate and Input Validation Layer."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.inference import InferenceResponse
from app.services.preprocessing_service import ImageValidationError, UnsupportedFormatError
from app.services.sonar_image_validator import (
    NonSonarImageError,
    SonarImageValidator,
    evaluate_sonar_likeness,
    sonar_validator,
)

client = TestClient(app)
client.post("/api/v1/session")

REAL_SAMPLE_PATH = Path("../frontend/public/assets/underwater_plate_final.jpg")


def _create_synthetic_sonar_bytes(format_name: str = "PNG", size=(640, 640)) -> bytes:
    """Generate near-monochrome acoustic slate sonar image."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(20, 30, 40))
    img.save(buf, format=format_name)
    buf.seek(0)
    return buf.read()


def _create_polychromatic_photo_bytes(format_name: str = "PNG", size=(400, 400)) -> bytes:
    """Generate colorful optical photograph with distinct red, green, blue color fields."""
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    third = size[1] // 3
    arr[:third, :, :] = [230, 50, 50]       # Bright red sky/object
    arr[third:2*third, :, :] = [50, 210, 50] # Bright green foliage
    arr[2*third:, :, :] = [40, 70, 240]      # Bright blue water/clothing
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    buf.seek(0)
    return buf.read()


# =========================================================================
# 1. Unit Tests for SonarImageValidator Service
# =========================================================================

def test_sonar_validator_real_sample_accepted():
    """Verify authentic side-scan sonar image is accepted by the validator."""
    if not REAL_SAMPLE_PATH.exists():
        pytest.skip(f"Sample image not found at {REAL_SAMPLE_PATH}")

    real_bytes = REAL_SAMPLE_PATH.read_bytes()
    report = sonar_validator.validate_upload(
        file_bytes=real_bytes,
        filename=REAL_SAMPLE_PATH.name,
        content_type="image/jpeg",
    )
    assert report.is_valid is True
    assert report.circular_variance < 0.20  # Tightly localized acoustic colormap


def test_sonar_validator_grayscale_accepted():
    """Verify raw monochrome/grayscale acoustic image passes validation."""
    gray_arr = np.random.randint(20, 200, (480, 640, 3), dtype=np.uint8)
    # Ensure R=G=B
    gray_arr[:, :, 1] = gray_arr[:, :, 0]
    gray_arr[:, :, 2] = gray_arr[:, :, 0]

    img = Image.fromarray(gray_arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    report = sonar_validator.validate_upload(
        file_bytes=buf.getvalue(),
        filename="grayscale_swath.png",
        content_type="image/png",
    )
    assert report.is_valid is True
    assert report.color_diff == 0.0


def test_sonar_validator_polychromatic_photo_rejected():
    """Verify colorful consumer photograph raises NonSonarImageError."""
    photo_bytes = _create_polychromatic_photo_bytes("PNG")

    with pytest.raises(NonSonarImageError) as exc_info:
        sonar_validator.validate_upload(
            file_bytes=photo_bytes,
            filename="landscape_photo.png",
            content_type="image/png",
        )
    assert "not appear to be a valid Side-Scan Sonar image" in str(exc_info.value)


def test_sonar_validator_blank_canvas_rejected():
    """Verify solid pure white canvas/document is rejected."""
    white_arr = np.full((300, 300, 3), 255, dtype=np.uint8)
    img = Image.fromarray(white_arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with pytest.raises(NonSonarImageError):
        sonar_validator.validate_upload(
            file_bytes=buf.getvalue(),
            filename="blank_document.png",
            content_type="image/png",
        )


def test_sonar_validator_corrupted_image_rejected():
    """Verify corrupted bytes raise ImageValidationError."""
    with pytest.raises(ImageValidationError):
        sonar_validator.validate_upload(
            file_bytes=b"CORRUPTED_NON_IMAGE_BINARY_STREAM",
            filename="bad_file.png",
            content_type="image/png",
        )


def test_sonar_validator_unsupported_format_rejected():
    """Verify unsupported file format raises UnsupportedFormatError."""
    with pytest.raises(UnsupportedFormatError):
        sonar_validator.validate_upload(
            file_bytes=b"fake data",
            filename="survey.txt",
            content_type="text/plain",
        )


# =========================================================================
# 2. API Boundary Verification (HTTP 422 vs HTTP 200)
# =========================================================================

def test_api_analyze_rejects_random_photo_with_422():
    """Verify POST /analyze rejects random photograph with HTTP 422 before ML inference."""
    photo_bytes = _create_polychromatic_photo_bytes("JPEG")
    files = {"image": ("holiday_photo.jpg", photo_bytes, "image/jpeg")}

    # Mock inference to verify that predict() is NEVER called for a non-sonar image
    with patch("app.services.inference.inference_service.predict") as mock_predict:
        response = client.post("/api/v1/analysis/analyze", files=files)
        mock_predict.assert_not_called()

    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "INVALID_SONAR_IMAGE"
    assert "does not appear to be a valid Side-Scan Sonar image" in data["message"]
    assert "Please upload a valid Side-Scan Sonar survey image." in data["details"]


def test_api_analyze_accepts_valid_sonar_with_zero_detections():
    """Verify valid sonar image with 0 detections is accepted and returns HTTP 200."""
    sonar_bytes = _create_synthetic_sonar_bytes("PNG")
    files = {"image": ("sonar_clear_waterfall.png", sonar_bytes, "image/png")}

    mock_resp = InferenceResponse(
        model_name="ghostvision",
        model_architecture="YOLO12s",
        detections_count=0,
        detections=[],
        image_width=640,
        image_height=640,
        inference_time_ms=5.0,
    )

    with patch("app.services.inference.inference_service.predict", return_value=mock_resp):
        response = client.post("/api/v1/analysis/analyze", files=files, data={"selected_models": "ghostvision"})

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "completed"
    assert res_json["summary"]["total_detections"] == 0
    assert len(res_json["detections"]) == 0
    assert "analysis_id" in res_json


def test_api_analyze_real_sonar_inference_works():
    """Verify real sonar plate passes validator and completes end-to-end inference."""
    if not REAL_SAMPLE_PATH.exists():
        pytest.skip(f"Sample image not found at {REAL_SAMPLE_PATH}")

    real_bytes = REAL_SAMPLE_PATH.read_bytes()
    files = {"image": ("underwater_plate_final.jpg", real_bytes, "image/jpeg")}
    data = {"selected_models": "ghostvision"}

    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "completed"
    assert "analysis_id" in res_json
    assert res_json["image"]["width"] == 1024
    assert res_json["image"]["height"] == 560


def test_sonar_validator_unsupported_mime_rejected():
    """Verify unsupported MIME type raises UnsupportedFormatError."""
    sonar_bytes = _create_synthetic_sonar_bytes("PNG")
    with pytest.raises(UnsupportedFormatError) as exc:
        sonar_validator.validate_upload(
            file_bytes=sonar_bytes,
            filename="valid_sonar.png",
            content_type="application/pdf",
        )
    assert "Unsupported MIME content type" in str(exc.value)


def test_sonar_validator_scanned_document_rejected():
    """Verify predominantly white document / page is rejected as non-sonar."""
    doc_arr = np.full((400, 400, 3), 250, dtype=np.uint8)
    doc_arr[40:360:15, 40:360] = 30  # Simulate lines of black text
    img = Image.fromarray(doc_arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with pytest.raises(NonSonarImageError) as exc:
        sonar_validator.validate_upload(
            file_bytes=buf.getvalue(),
            filename="scanned_report.png",
            content_type="image/png",
        )
    assert "not appear to be a valid Side-Scan Sonar image" in str(exc.value)


def test_sonar_validator_solid_black_rejected():
    """Verify solid black image with zero acoustic signal is rejected."""
    black_arr = np.zeros((300, 300, 3), dtype=np.uint8)
    img = Image.fromarray(black_arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with pytest.raises(NonSonarImageError):
        sonar_validator.validate_upload(
            file_bytes=buf.getvalue(),
            filename="black_canvas.png",
            content_type="image/png",
        )


def test_api_analyze_rejects_unsupported_mime_with_415():
    """Verify API returns HTTP 415 when unsupported MIME is provided."""
    sonar_bytes = _create_synthetic_sonar_bytes("PNG")
    files = {"image": ("sonar_data.png", sonar_bytes, "application/pdf")}

    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 415
    assert "Unsupported" in response.json()["detail"]


def test_api_analyze_rejects_corrupted_image_with_400():
    """Verify API returns HTTP 400 when corrupted image is uploaded."""
    files = {"image": ("corrupted.png", b"NOT_VALID_IMAGE_DATA_12345", "image/png")}

    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 400
    assert "Corrupted or invalid image stream" in response.json()["detail"]


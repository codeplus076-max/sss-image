"""Comprehensive tests for Backend Metadata, Geolocation Integrity, and GIS Foundation."""

import io
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app

from unittest.mock import patch
from app.schemas.inference import InferenceResponse

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_predict_for_metadata_tests():
    """Mock inference_service.predict so metadata tests execute fast without GPU/PyTorch RAM exhaustion."""
    def _mock_predict(name_or_key, *args, **kwargs):
        return InferenceResponse(
            model_name=name_or_key,
            model_architecture="YOLO",
            image_width=128,
            image_height=128,
            inference_time_ms=2.0,
            detections_count=0,
            detections=[],
        )

    with patch("app.services.analysis_service.inference_service.predict", side_effect=_mock_predict), \
         patch("app.services.inference.inference_service.predict", side_effect=_mock_predict):
        yield


def _make_dummy_sonar_bytes(size=(128, 128), color=(20, 30, 40)) -> bytes:
    """Generate dummy near-monochrome sonar image bytes that pass the validator gate."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _make_polychromatic_photo_bytes(size=(200, 200)) -> bytes:
    """Generate colorful RGB image that fails sonar validation gate."""
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    h = size[1] // 3
    arr[:h, :, :] = [240, 40, 40]
    arr[h:2*h, :, :] = [40, 240, 40]
    arr[2*h:, :, :] = [40, 40, 240]
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# =========================================================================
# A. Valid Latitude + Longitude Accepted
# =========================================================================

def test_valid_latitude_and_longitude_accepted():
    """Verify analysis accepts valid coordinates and returns accurate metadata and geolocation."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("survey_geo.png", img_bytes, "image/png")}
    data = {
        "latitude": 18.9169,
        "longitude": 72.8365,
        "depth": 42.5,
        "heading": 135.0,
        "timestamp": "2026-09-30T10:15:30Z",
    }
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    res = response.json()

    # Verify metadata field
    assert "metadata" in res
    meta = res["metadata"]
    assert meta["latitude"] == 18.9169
    assert meta["longitude"] == 72.8365
    assert meta["depth"] == 42.5
    assert meta["heading"] == 135.0
    assert meta["timestamp"] == "2026-09-30T10:15:30Z"
    assert meta["geolocation_available"] is True

    # Verify backward-compatible geolocation field
    assert "geolocation" in res
    geo = res["geolocation"]
    assert geo["latitude"] == 18.9169
    assert geo["longitude"] == 72.8365
    assert geo["depth_m"] == 42.5
    assert geo["heading"] == 135.0
    assert geo["timestamp"] == "2026-09-30T10:15:30Z"
    assert geo["geolocation_available"] is True


# =========================================================================
# B. Missing Latitude + Longitude Accepted (Image-only mode)
# =========================================================================

def test_missing_latitude_and_longitude_accepted():
    """Verify analysis accepts missing coordinates without fabricating mock values."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("sonar_no_geo.png", img_bytes, "image/png")}
    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 200
    res = response.json()

    # Metadata structure present with None/null values
    assert "metadata" in res
    meta = res["metadata"]
    assert meta["latitude"] is None
    assert meta["longitude"] is None
    assert meta["depth"] is None
    assert meta["heading"] is None
    assert meta["timestamp"] is None
    assert meta["geolocation_available"] is False

    # Geolocation structure present with None/null values
    assert "geolocation" in res
    geo = res["geolocation"]
    assert geo["latitude"] is None
    assert geo["longitude"] is None
    assert geo["depth_m"] is None
    assert geo["heading"] is None
    assert geo["timestamp"] is None
    assert geo["geolocation_available"] is False


# =========================================================================
# C. Invalid Latitude Rejected
# =========================================================================

@pytest.mark.parametrize("invalid_lat", [91.0, -91.0, 180.0, "north", "invalid"])
def test_invalid_latitude_rejected(invalid_lat):
    """Verify latitude outside [-90.0, 90.0] or non-numeric returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"latitude": invalid_lat}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Latitude" in response.json()["detail"]


# =========================================================================
# D. Invalid Longitude Rejected
# =========================================================================

@pytest.mark.parametrize("invalid_lon", [181.0, -181.0, 270.0, "east", "invalid"])
def test_invalid_longitude_rejected(invalid_lon):
    """Verify longitude outside [-180.0, 180.0] or non-numeric returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"longitude": invalid_lon}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Longitude" in response.json()["detail"]


# =========================================================================
# E. Invalid Depth Rejected
# =========================================================================

@pytest.mark.parametrize("invalid_depth", [-1.0, -45.5, "negative", "invalid"])
def test_invalid_depth_rejected(invalid_depth):
    """Verify negative depth or non-numeric value returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"depth": invalid_depth}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Depth" in response.json()["detail"]


# =========================================================================
# F. Invalid Heading Rejected
# =========================================================================

@pytest.mark.parametrize("invalid_heading", [360.0, 361.0, -0.5, -90.0, 420.0, "portside"])
def test_invalid_heading_rejected(invalid_heading):
    """Verify heading outside [0.0, 360.0) or non-numeric returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"heading": invalid_heading}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Heading" in response.json()["detail"]


def test_valid_boundary_headings_accepted():
    """Verify boundary heading values (0.0 and 359.9) are accepted."""
    img_bytes = _make_dummy_sonar_bytes()
    for h in [0.0, 180.0, 359.9]:
        files = {"image": ("test.png", img_bytes, "image/png")}
        data = {"heading": h}
        response = client.post("/api/v1/analysis/analyze", files=files, data=data)
        assert response.status_code == 200
        assert response.json()["metadata"]["heading"] == h


# =========================================================================
# G. Invalid Timestamp Rejected
# =========================================================================

@pytest.mark.parametrize("invalid_ts", [
    "not-a-timestamp",
    "2026/09/30",
    "yesterday",
    "2026-99-99T99:99:99",
    "12345",
])
def test_invalid_timestamp_rejected(invalid_ts):
    """Verify malformed or non-ISO timestamp string returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"timestamp": invalid_ts}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Timestamp" in response.json()["detail"]


def test_valid_iso_timestamps_accepted():
    """Verify valid ISO-8601 timestamps are accepted."""
    img_bytes = _make_dummy_sonar_bytes()
    valid_stamps = [
        "2026-09-30T10:00:00Z",
        "2026-09-30T15:30:00+05:30",
        "2026-09-30T08:00:00.123Z",
        "2026-09-30",
    ]
    for ts in valid_stamps:
        files = {"image": ("test.png", img_bytes, "image/png")}
        data = {"timestamp": ts}
        response = client.post("/api/v1/analysis/analyze", files=files, data=data)
        assert response.status_code == 200
        assert response.json()["metadata"]["timestamp"] == ts


# =========================================================================
# H. No Fake Coordinates Generated
# =========================================================================

def test_no_fake_coordinates_generated():
    """Verify image-only uploads strictly maintain null coordinates and UNAVAILABLE references."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("sonar_clean.png", img_bytes, "image/png")}
    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["metadata"]["latitude"] is None
    assert data["metadata"]["longitude"] is None
    assert data["metadata"]["geolocation_available"] is False

    assert data["geolocation"]["latitude"] is None
    assert data["geolocation"]["longitude"] is None
    assert data["geolocation"]["geolocation_available"] is False

    # Check individual detections if any exist
    for det in data.get("detections", []):
        assert det.get("latitude") is None
        assert det.get("longitude") is None
        assert det.get("geoLat") is None
        assert det.get("geoLon") is None
        assert det.get("coordinateReference") == "UNAVAILABLE"
        assert det.get("metadataSource") == "Image-only sonar input"


# =========================================================================
# I. Image-only Analysis Remains Valid
# =========================================================================

def test_image_only_analysis_remains_valid():
    """Verify that uploading only an image file with zero metadata runs cleanly."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("sonar_only.png", img_bytes, "image/png")}
    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert data["analysis_id"].startswith("SONAR-")
    assert data["image"]["filename"] == "sonar_only.png"
    assert data["image"]["width"] == 128
    assert data["image"]["height"] == 128
    assert data["evidence_url"].startswith("/api/v1/analysis/SONAR-")


# =========================================================================
# J. Metadata is Persisted and Returned in All Retrieval Endpoints
# =========================================================================

def test_metadata_persisted_and_returned_in_endpoints():
    """Verify metadata is saved in SQLite and returned by GET /{id} and GET /."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("survey_transect.png", img_bytes, "image/png")}
    data = {
        "latitude": 15.2993,
        "longitude": 73.9877,
        "depth": 28.4,
        "heading": 85.0,
        "timestamp": "2026-09-30T12:00:00Z",
    }
    # 1. POST
    post_res = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert post_res.status_code == 200
    analysis_id = post_res.json()["analysis_id"]

    # 2. GET by ID
    get_res = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["metadata"]["latitude"] == 15.2993
    assert detail["metadata"]["longitude"] == 73.9877
    assert detail["metadata"]["depth"] == 28.4
    assert detail["metadata"]["heading"] == 85.0
    assert detail["metadata"]["timestamp"] == "2026-09-30T12:00:00Z"
    assert detail["metadata"]["geolocation_available"] is True

    # 3. GET list
    list_res = client.get("/api/v1/analysis?page=1&page_size=10")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    target_item = next((it for it in items if it["analysis_id"] == analysis_id), None)
    assert target_item is not None
    assert target_item["metadata"]["geolocation_available"] is True
    assert target_item["metadata"]["latitude"] == 15.2993


# =========================================================================
# K. Evidence Endpoint Continues Working
# =========================================================================

def test_evidence_endpoint_retrieval():
    """Verify stored evidence image is streamed accurately."""
    img_bytes = _make_dummy_sonar_bytes(size=(64, 64))
    files = {"image": ("test_ev.png", img_bytes, "image/png")}
    post_res = client.post("/api/v1/analysis/analyze", files=files)
    assert post_res.status_code == 200
    analysis_id = post_res.json()["analysis_id"]

    # Fetch evidence
    ev_res = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert ev_res.status_code == 200
    assert ev_res.headers.get("content-type") == "image/png"
    assert len(ev_res.content) == len(img_bytes)


# =========================================================================
# L. Existing Model Selection Still Works
# =========================================================================

def test_model_selection_subset():
    """Verify requesting model subsets functions accurately."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test_models.png", img_bytes, "image/png")}
    data = {"selected_models": "ghostvision,subpipes"}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    models_run = response.json()["summary"]["models_executed"]
    assert "ghostvision" in models_run
    assert "subpipes" in models_run


# =========================================================================
# M. Natural Seabed Is Available & Executes Stage 1 Triage
# =========================================================================

def test_natural_seabed_available_and_executes():
    """Verify requesting Natural Seabed model returns HTTP 200 and performs triage."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test_seabed.png", img_bytes, "image/png")}
    data = {"selected_models": "natural_seabed"}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["triage"] is not None
    assert "clean_probability" in data["triage"]
    assert "natural_seabed" in data["summary"]["models_executed"]


# =========================================================================
# N. Existing Random Image Rejection Still Works
# =========================================================================

def test_random_image_rejection_at_gate():
    """Verify polychromatic photo is rejected at sonar gate with HTTP 422."""
    photo_bytes = _make_polychromatic_photo_bytes()
    files = {"image": ("vacation.png", photo_bytes, "image/png")}
    response = client.post("/api/v1/analysis/analyze", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "INVALID_SONAR_IMAGE"
    assert "valid Side-Scan Sonar" in data["message"]


# =========================================================================
# O. Inference Thresholds (Confidence & IoU) & Coordinate Separation
# =========================================================================

@pytest.mark.parametrize("invalid_conf", [-0.01, 1.01, 2.5, -1.0, "high", "invalid"])
def test_invalid_confidence_rejected(invalid_conf):
    """Verify confidence threshold outside [0.0 - 1.0] or non-numeric returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"confidence": invalid_conf}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "Confidence threshold" in response.json()["detail"]


@pytest.mark.parametrize("invalid_iou", [-0.05, 1.05, 1.5, -2.0, "loose", "invalid"])
def test_invalid_iou_rejected(invalid_iou):
    """Verify IoU threshold outside [0.0 - 1.0] or non-numeric returns HTTP 400."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"iou": invalid_iou}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 400
    assert "IoU threshold" in response.json()["detail"]


def test_valid_confidence_and_iou_accepted():
    """Verify valid confidence and IoU thresholds within [0.0 - 1.0] are accepted."""
    img_bytes = _make_dummy_sonar_bytes()
    files = {"image": ("test.png", img_bytes, "image/png")}
    data = {"confidence": 0.35, "iou": 0.50}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_partial_coordinates_remain_unavailable():
    """Verify that providing only latitude without longitude (or vice-versa) preserves geolocation_available=False."""
    img_bytes = _make_dummy_sonar_bytes()
    # Case 1: Latitude only
    files = {"image": ("test_lat_only.png", img_bytes, "image/png")}
    data = {"latitude": 18.9169}
    response = client.post("/api/v1/analysis/analyze", files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["metadata"]["latitude"] == 18.9169
    assert res["metadata"]["longitude"] is None
    assert res["metadata"]["geolocation_available"] is False

    # Case 2: Longitude only
    files2 = {"image": ("test_lon_only.png", img_bytes, "image/png")}
    data2 = {"longitude": 72.8365}
    response2 = client.post("/api/v1/analysis/analyze", files=files2, data=data2)
    assert response2.status_code == 200
    res2 = response2.json()
    assert res2["metadata"]["latitude"] is None
    assert res2["metadata"]["longitude"] == 72.8365
    assert res2["metadata"]["geolocation_available"] is False


def test_detection_image_space_coordinates_distinction():
    """Verify detections strictly maintain image-space bounding box geometry separate from survey GPS."""
    from app.schemas.inference import BoundingBox, DetectionResult

    mock_bbox = BoundingBox(
        x1=100.0, y1=120.0, x2=250.0, y2=300.0, width=150.0, height=180.0,
        norm_x1=0.1, norm_y1=0.12, norm_w=0.15, norm_h=0.18
    )
    mock_det = DetectionResult(
        model_name="cylinder",
        class_id=0,
        raw_class_name="Cylinder",
        semantic_class_name="Industrial Cylinder / Drum",
        confidence=0.89,
        bounding_box=mock_bbox,
        image_width=1000,
        image_height=1000,
    )
    mock_resp = InferenceResponse(
        model_name="cylinder", model_architecture="YOLO12s",
        detections_count=1, detections=[mock_det], image_width=1000, image_height=1000, inference_time_ms=10.0
    )

    with patch("app.services.analysis_service.inference_service.predict", return_value=mock_resp):
        img_bytes = _make_dummy_sonar_bytes(size=(1000, 1000))
        files = {"image": ("transect_01.png", img_bytes, "image/png")}
        data = {
            "selected_models": "cylinder",
            "latitude": 15.2993,
            "longitude": 73.9877,
            "depth": 35.0,
            "heading": 90.0,
        }
        response = client.post("/api/v1/analysis/analyze", files=files, data=data)
        assert response.status_code == 200
        res = response.json()

        # Survey Geolocation
        assert res["metadata"]["latitude"] == 15.2993
        assert res["metadata"]["longitude"] == 73.9877
        assert res["metadata"]["geolocation_available"] is True

        # Detection Image-Space Coordinates
        det = res["detections"][0]
        assert det["model"] == "cylinder"
        assert det["bbox"]["x1"] == 100.0
        assert det["bbox"]["y1"] == 120.0
        assert det["bbox"]["x2"] == 250.0
        assert det["bbox"]["y2"] == 300.0
        assert det["bbox"]["width"] == 150.0
        assert det["bbox"]["height"] == 180.0
        assert det["bbox"]["norm_x1"] == 0.1
        assert det["bbox"]["norm_y1"] == 0.12
        assert det["bbox"]["x"] == 10.0
        assert det["bbox"]["y"] == 12.0
        assert det["display_class"] == "Cylinder"
        assert det["category"] == "Cylinder"


def test_detection_normalization_all_known_classes():
    """Verify clean normalized detection representation for all required known classes."""
    from app.services.detection_normalizer import normalize_class_name, get_category_name

    mappings = [
        ("Cylinder", "Cylinder", "Cylinder"),
        ("Crab-Pot", "Ghost Gear", "Ghost Gear / Crab Pot"),
        ("Pipeline", "Subsea Pipeline", "Subsea Pipeline"),
        ("Shipwreck", "Shipwreck", "Shipwreck"),
        ("MILCO", "Mine-Like Contact", "Mine-Like Contact"),
        ("NOMBO", "Non-Mine Mine-Like Bottom Object", "Non-Mine Mine-Like Bottom Object"),
        ("Class_0", "Class_0 (Unknown / Unlabeled)", "Unknown / Unlabeled Artifact"),
    ]

    for raw, expected_display, expected_cat in mappings:
        assert normalize_class_name(raw) == expected_display
        assert get_category_name(raw) == expected_cat


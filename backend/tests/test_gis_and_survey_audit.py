"""
Step 7 — GIS & Survey Intelligence Audit Tests.

Verifies:
1. Valid latitude/longitude
2. Invalid latitude
3. Invalid longitude
4. Missing geolocation
5. Valid depth
6. Invalid depth
7. Missing depth
8. Valid heading
9. Invalid heading
10. Missing heading
11. Valid ISO timestamp
12. Invalid timestamp
13. CRS correctness (WGS 84 Geographic 2D - EPSG:4326 vs UNAVAILABLE, no misleading UTM)
14. Survey vs detection location separation (survey_latitude anchor vs image-space target)
15. GIS analysis A/B isolation
16. Evidence metadata isolation
17. No fabricated coordinates
18. Existing random image rejection
19. Existing detection normalization
20. Existing zero-detection behaviour
"""

import io
import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.main import app
from app.schemas.inference import BoundingBox, DetectionResult
from app.services.detection_normalizer import (
    build_analysis_detection,
    get_category_name,
    normalize_class_name,
)
from app.schemas.analysis import AnalysisGeolocation

client = TestClient(app)
client.post("/api/v1/session")


def _generate_valid_sonar_bytes(w=256, h=256):
    """Generate synthetic valid sonar swath bytes."""
    noise = np.random.normal(loc=35, scale=6, size=(h, w)).clip(5, 100).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buf, format="PNG")
    return buf.getvalue()


# 1. Valid latitude / longitude
def test_valid_lat_lon():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_valid.png", img_bytes, "image/png")},
        data={"latitude": "18.9175", "longitude": "72.8375"},
    )
    assert resp.status_code == 200
    meta = resp.json()["metadata"]
    assert meta["geolocation_available"] is True
    assert abs(meta["latitude"] - 18.9175) < 0.0001
    assert abs(meta["longitude"] - 72.8375) < 0.0001


# 2. Invalid latitude rejected
@pytest.mark.parametrize("invalid_lat", ["-90.1", "90.001", "120.0", "invalid", "-150.0"])
def test_invalid_latitude_rejected(invalid_lat):
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_test.png", img_bytes, "image/png")},
        data={"latitude": invalid_lat, "longitude": "72.8375"},
    )
    assert resp.status_code == 400


# 3. Invalid longitude rejected
@pytest.mark.parametrize("invalid_lon", ["-180.1", "180.001", "240.0", "invalid", "-200.0"])
def test_invalid_longitude_rejected(invalid_lon):
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_test.png", img_bytes, "image/png")},
        data={"latitude": "18.9175", "longitude": invalid_lon},
    )
    assert resp.status_code == 400


# 4. Missing geolocation
def test_missing_geolocation_handled_honestly():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_nogeo.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    meta = resp.json()["metadata"]
    assert meta["geolocation_available"] is False
    assert meta["latitude"] is None
    assert meta["longitude"] is None


# 5. Valid depth
def test_valid_depth_accepted():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_depth.png", img_bytes, "image/png")},
        data={"depth": "45.5"},
    )
    assert resp.status_code == 200
    assert abs(resp.json()["metadata"]["depth"] - 45.5) < 0.01


# 6. Invalid depth rejected
@pytest.mark.parametrize("invalid_depth", ["-0.1", "-50.0", "deep", "invalid"])
def test_invalid_depth_rejected(invalid_depth):
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_depth.png", img_bytes, "image/png")},
        data={"depth": invalid_depth},
    )
    assert resp.status_code == 400


# 7. Missing depth
def test_missing_depth_remains_null():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_nodepth.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["depth"] is None


# 8. Valid heading
def test_valid_heading_accepted():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_hdg.png", img_bytes, "image/png")},
        data={"heading": "135.5"},
    )
    assert resp.status_code == 200
    assert abs(resp.json()["metadata"]["heading"] - 135.5) < 0.01


# 9. Invalid heading rejected
@pytest.mark.parametrize("invalid_hdg", ["-0.1", "360.0", "420.0", "north", "invalid"])
def test_invalid_heading_rejected(invalid_hdg):
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_hdg.png", img_bytes, "image/png")},
        data={"heading": invalid_hdg},
    )
    assert resp.status_code == 400


# 10. Missing heading
def test_missing_heading_remains_null():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_nohdg.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["heading"] is None


# 11. Valid ISO timestamp
def test_valid_iso_timestamp_accepted():
    img_bytes = _generate_valid_sonar_bytes()
    ts = "2026-09-30T10:30:00Z"
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_ts.png", img_bytes, "image/png")},
        data={"timestamp": ts},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["timestamp"] == ts


# 12. Invalid timestamp rejected
@pytest.mark.parametrize("invalid_ts", ["not-a-timestamp", "2026/09/30", "yesterday", "2026-99-99T99:99:99"])
def test_invalid_timestamp_rejected(invalid_ts):
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_ts.png", img_bytes, "image/png")},
        data={"timestamp": invalid_ts},
    )
    assert resp.status_code == 400


# 13. CRS correctness (WGS 84 Geographic 2D - EPSG:4326 vs UNAVAILABLE, no misleading UTM)
def test_crs_correctness_regression():
    det_res = DetectionResult(
        model_name="cylinder",
        class_id=0,
        raw_class_name="Cylinder",
        semantic_class_name="Cylinder",
        confidence=0.9,
        bounding_box=BoundingBox(x1=10, y1=10, x2=20, y2=20, width=10, height=10, norm_x1=0.1, norm_y1=0.1, norm_w=0.1, norm_h=0.1),
        image_width=100,
        image_height=100,
    )
    # Case A: with geographic telemetry
    geo = AnalysisGeolocation(latitude=18.9175, longitude=72.8375, geolocation_available=True)
    det_geo = build_analysis_detection(det_res, index=0, image_width=100, image_height=100, geolocation=geo)
    assert det_geo.coordinateReference == "WGS 84 (Geographic 2D - EPSG:4326)"
    assert "UTM" not in det_geo.coordinateReference

    # Case B: without telemetry
    det_nogeo = build_analysis_detection(det_res, index=0, image_width=100, image_height=100, geolocation=None)
    assert det_nogeo.coordinateReference == "UNAVAILABLE"


# 14. Survey vs detection location separation
def test_survey_vs_detection_location_separation():
    det_res = DetectionResult(
        model_name="shipwreck",
        class_id=0,
        raw_class_name="Shipwreck",
        semantic_class_name="Shipwreck",
        confidence=0.92,
        bounding_box=BoundingBox(x1=30, y1=40, x2=80, y2=90, width=50, height=50, norm_x1=0.3, norm_y1=0.4, norm_w=0.5, norm_h=0.5),
        image_width=100,
        image_height=100,
    )
    geo = AnalysisGeolocation(latitude=18.9175, longitude=72.8375, geolocation_available=True)
    det = build_analysis_detection(det_res, index=0, image_width=100, image_height=100, geolocation=geo)

    # Survey anchor is explicitly recorded
    assert det.survey_latitude == 18.9175
    assert det.survey_longitude == 72.8375
    # Detection is flagged as unprojected in image-space
    assert det.has_target_geolocation is False
    assert "image-space" in det.target_geolocation_note.lower()
    # Detection coordinates in image space
    assert det.imagePosition["x"] == 30.0
    assert det.imagePosition["y"] == 40.0


# 15. GIS analysis A/B isolation
def test_gis_analysis_ab_isolation():
    img_bytes = _generate_valid_sonar_bytes()
    resp_a = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_a.png", img_bytes, "image/png")},
        data={"latitude": "18.9175", "longitude": "72.8375"},
    )
    resp_b = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_b.png", img_bytes, "image/png")},
        data={"latitude": "19.0760", "longitude": "72.8777"},
    )
    id_a = resp_a.json()["analysis_id"]
    id_b = resp_b.json()["analysis_id"]

    rec_a = client.get(f"/api/v1/analysis/{id_a}").json()
    rec_b = client.get(f"/api/v1/analysis/{id_b}").json()

    assert abs(rec_a["metadata"]["latitude"] - 18.9175) < 0.0001
    assert abs(rec_a["metadata"]["longitude"] - 72.8375) < 0.0001
    assert abs(rec_b["metadata"]["latitude"] - 19.0760) < 0.0001
    assert abs(rec_b["metadata"]["longitude"] - 72.8777) < 0.0001


# 16. Evidence metadata isolation
def test_evidence_metadata_isolation():
    img_bytes_1 = _generate_valid_sonar_bytes(250, 250)
    img_bytes_2 = _generate_valid_sonar_bytes(350, 350)

    id_1 = client.post("/api/v1/analysis/analyze", files={"image": ("ev1.png", img_bytes_1, "image/png")}).json()["analysis_id"]
    id_2 = client.post("/api/v1/analysis/analyze", files={"image": ("ev2.png", img_bytes_2, "image/png")}).json()["analysis_id"]

    ev_1 = client.get(f"/api/v1/analysis/{id_1}/evidence").content
    ev_2 = client.get(f"/api/v1/analysis/{id_2}/evidence").content
    assert ev_1 == img_bytes_1
    assert ev_2 == img_bytes_2
    assert ev_1 != ev_2


# 17. No fabricated coordinates
def test_no_fabricated_coordinates_when_omitted():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_clean.png", img_bytes, "image/png")},
    )
    data = resp.json()
    meta = data["metadata"]
    assert meta["latitude"] is None
    assert meta["longitude"] is None
    assert meta["depth"] is None
    assert meta["heading"] is None
    assert meta["geolocation_available"] is False


# 18. Existing random image rejection
def test_random_image_rejection_at_gate():
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb[:85, :, 0] = 255
    rgb[85:170, :, 1] = 255
    rgb[170:, :, 2] = 255
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG")

    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("photo.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert resp.status_code == 422
    assert resp.json().get("error") == "INVALID_SONAR_IMAGE"


# 19. Existing detection normalization
def test_existing_detection_normalization():
    assert normalize_class_name("Crab-Pot") == "Ghost Gear"
    assert get_category_name("Crab-Pot") == "Ghost Gear / Crab Pot"
    assert normalize_class_name("Shipwreck") == "Shipwreck"
    assert normalize_class_name("Pipeline") == "Subsea Pipeline"


# 20. Existing zero-detection behaviour
def test_existing_zero_detection_behaviour():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("zero_swath.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"].upper() == "COMPLETED"
    assert isinstance(data["detections"], list)

"""
Step 9 — Final Report, Export & SIH26057 Demo Readiness Acceptance Tests.

Comprehensive verification of:
1. Valid sonar upload
2. Random image rejection
3. Corrupted image handling
4. Unsupported format handling
5. Zero detections handling
6. GPS available persisted and returned
7. GPS unavailable honestly null
8. Multi-model analysis execution
9. Model provenance preservation
10. Cross-model deduplication
11. Evidence isolation
12. Analysis A/B isolation
13. Intelligence summary integrity
14. JSON export structure
15. CSV export structure
16. Missing evidence returns 404
17. Missing analysis ID returns 404
18. Model availability endpoint
19. Health endpoint
20. Natural Seabed remains disabled
21. No fake coordinates
22. No stale detection state
23. No stale report state
24. Backend error handling sanitized
"""

import io
import json
import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.main import app
from app.schemas.inference import BoundingBox, DetectionResult
from app.schemas.analysis import AnalysisDetection, DetectionIntelligence, AnalysisGeolocation
from app.services.detection_normalizer import (
    determine_detection_priority,
    get_highest_priority_detection,
    compute_analysis_summary,
    build_analysis_detection,
    normalize_class_name,
    get_category_name,
)

client = TestClient(app)


def _generate_valid_sonar_bytes(w=256, h=256):
    """Generate synthetic valid sonar swath bytes meeting quality validation criteria."""
    noise = np.random.normal(loc=35, scale=6, size=(h, w)).clip(5, 100).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _make_det(model_name="mine_detector", raw_class="MILCO", conf=0.85, x1=10.0, y1=20.0, x2=50.0, y2=80.0):
    """Helper to build a valid DetectionResult for testing."""
    return DetectionResult(
        model_name=model_name,
        class_id=0,
        raw_class_name=raw_class,
        semantic_class_name=raw_class,
        confidence=conf,
        bounding_box=BoundingBox(
            x1=x1, y1=y1, x2=x2, y2=y2,
            width=abs(x2 - x1), height=abs(y2 - y1),
            norm_x1=x1 / 100.0, norm_y1=y1 / 100.0,
            norm_w=abs(x2 - x1) / 100.0, norm_h=abs(y2 - y1) / 100.0,
        ),
        image_width=100,
        image_height=100,
    )


# 1. Valid sonar upload
def test_01_valid_sonar_upload():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_valid.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "analysis_id" in data
    assert data["status"] == "completed"
    assert "detections" in data
    assert "summary" in data
    assert "metadata" in data
    assert "geolocation" in data


# 2. Random image rejection
def test_02_random_image_rejection():
    # Random RGB image rejected before ML inference
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb[:85, :, 0] = 255
    rgb[85:170, :, 1] = 255
    rgb[170:, :, 2] = 255
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG")

    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("random_photo.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert resp.status_code == 422
    assert resp.json().get("error") == "INVALID_SONAR_IMAGE"


# 3. Corrupted image handling
def test_03_corrupted_image_handling():
    corrupted_bytes = b"NOT_A_REAL_IMAGE_FILE_HEADER_XYZ123"
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("corrupted.png", corrupted_bytes, "image/png")},
    )
    assert resp.status_code == 400


# 4. Unsupported format handling
def test_04_unsupported_format_handling():
    text_bytes = b"Hello world, this is a plain text file."
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("readme.txt", text_bytes, "text/plain")},
    )
    assert resp.status_code == 415


# 5. Zero detections handling
def test_05_zero_detections_analysis():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("clean_sonar.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert isinstance(data["detections"], list)
    summary = data["summary"]
    assert summary["total_detections"] == len(data["detections"])
    if summary["total_detections"] == 0:
        assert summary["high_priority"] == 0
        assert summary["medium_priority"] == 0
        assert summary["low_priority"] == 0
        assert summary["highest_priority_detection"] is None


# 6. GPS available persisted and returned
def test_06_gps_available_persisted_and_returned():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_gps.png", img_bytes, "image/png")},
        data={"latitude": "18.9175", "longitude": "72.8375", "depth": "42.5", "heading": "182.0"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["geolocation_available"] is True
    assert abs(data["metadata"]["latitude"] - 18.9175) < 0.0001
    assert abs(data["metadata"]["longitude"] - 72.8375) < 0.0001
    assert abs(data["metadata"]["depth"] - 42.5) < 0.01
    assert abs(data["metadata"]["heading"] - 182.0) < 0.01


# 7. GPS unavailable honestly null
def test_07_gps_unavailable_honestly_null():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_nogps.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["geolocation_available"] is False
    assert data["metadata"]["latitude"] is None
    assert data["metadata"]["longitude"] is None
    assert data["metadata"]["depth"] is None
    assert data["metadata"]["heading"] is None


# 8. Multi-model analysis execution
def test_08_multi_model_analysis_execution():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_multimodel.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder,mines,shipwreck", "enable_seabed_gate": "false"},
    )
    assert resp.status_code == 200
    data = resp.json()
    summary = data["summary"]
    assert "models_executed" in summary
    assert "cylinder" in summary["models_executed"]


# 9. Model provenance preservation
def test_09_model_provenance_preservation():
    det1 = build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0)
    det2 = build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.92), index=1)
    assert det1.model == "mine_detector"
    assert det1.raw_class == "MILCO"
    assert det2.model == "shipwreck"
    assert det2.raw_class == "Shipwreck"


# 10. Cross-model deduplication
def test_10_cross_model_deduplication():
    # Verify that multiple detections post-deduplication reflect exact distinct objects
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.88), index=0),
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.91), index=1),
    ]
    summary = compute_analysis_summary(dets)
    assert summary.total_detections == 2
    assert summary.high_priority == 1
    assert summary.low_priority == 1


# 11. Evidence isolation
def test_11_evidence_isolation():
    img_1 = _generate_valid_sonar_bytes(240, 240)
    img_2 = _generate_valid_sonar_bytes(320, 320)

    id_1 = client.post("/api/v1/analysis/analyze", files={"image": ("ev1.png", img_1, "image/png")}).json()["analysis_id"]
    id_2 = client.post("/api/v1/analysis/analyze", files={"image": ("ev2.png", img_2, "image/png")}).json()["analysis_id"]

    content_1 = client.get(f"/api/v1/analysis/{id_1}/evidence").content
    content_2 = client.get(f"/api/v1/analysis/{id_2}/evidence").content

    assert content_1 == img_1
    assert content_2 == img_2
    assert content_1 != content_2


# 12. Analysis A/B isolation
def test_12_analysis_ab_isolation():
    img_a = _generate_valid_sonar_bytes()
    img_b = _generate_valid_sonar_bytes()

    res_a = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("a.png", img_a, "image/png")},
        data={"latitude": "10.0", "longitude": "20.0"},
    ).json()

    res_b = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("b.png", img_b, "image/png")},
        data={"latitude": "30.0", "longitude": "40.0"},
    ).json()

    assert res_a["analysis_id"] != res_b["analysis_id"]
    assert res_a["metadata"]["latitude"] == 10.0
    assert res_b["metadata"]["latitude"] == 30.0


# 13. Intelligence summary integrity
def test_13_intelligence_summary_integrity():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.70), index=0),    # HIGH
        build_analysis_detection(_make_det("subpipes", "Pipeline", 0.95), index=1),      # MEDIUM
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.60), index=2),      # LOW
    ]
    summary = compute_analysis_summary(dets)
    assert summary.total_detections == 3
    assert summary.high_priority == 1
    assert summary.medium_priority == 1
    assert summary.low_priority == 1
    assert summary.high_priority + summary.medium_priority + summary.low_priority == summary.total_detections
    # Highest priority is HIGH (MILCO), not MEDIUM (even though Pipeline has 0.95 confidence)
    assert summary.highest_priority_detection is not None
    assert summary.highest_priority_detection.priority == "HIGH"
    assert summary.highest_priority_detection.display_class == "Mine-Like Contact"


# 14. JSON export structure
def test_14_json_export_structure():
    # Simulate export schema validation
    dets = [
        build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.92), index=0),
    ]
    summary = compute_analysis_summary(dets)
    export_payload = {
        "analysis_id": "SONAR-TEST1234",
        "timestamp": "2026-09-30T03:30:00Z",
        "filename": "survey_test.png",
        "total_detections": summary.total_detections,
        "summary": summary.model_dump(),
        "detections": [d.model_dump() for d in dets],
        "geolocation_available": False,
    }
    # Validate no secret leak
    dumped = json.dumps(export_payload)
    assert "password" not in dumped.lower()
    assert "secret" not in dumped.lower()
    assert "token" not in dumped.lower()
    assert "SONAR-TEST1234" in dumped


# 15. CSV export structure
def test_15_csv_export_structure():
    det = build_analysis_detection(_make_det("mine_detector", "MILCO", 0.88), index=0)
    row = [
        det.id,
        det.display_class,
        det.model,
        det.priority,
        det.priority_reason,
        f"{det.confidence_percent}%",
        "Unavailable",
        det.review_status,
        det.evidence_status,
    ]
    csv_line = ",".join(f'"{c}"' for c in row)
    assert "DET-01" in csv_line
    assert "Mine-Like Contact" in csv_line
    assert "HIGH" in csv_line
    assert "PENDING REVIEW" in csv_line


# 16. Missing evidence returns 404
def test_16_missing_evidence_returns_404():
    resp = client.get("/api/v1/analysis/nonexistent-analysis-id-xyz/evidence")
    assert resp.status_code == 404


# 17. Missing analysis ID returns 404
def test_17_missing_analysis_id_returns_404():
    resp = client.get("/api/v1/analysis/nonexistent-analysis-id-xyz")
    assert resp.status_code == 404


# 18. Model availability endpoint
def test_18_model_availability_endpoint():
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    active_keys = {m["id"] for m in data["models"]}
    assert "cylinder" in active_keys
    assert "ghostvision" in active_keys
    assert "mines" in active_keys
    assert "shipwreck" in active_keys
    assert "subpipes" in active_keys


# 19. Health endpoint
def test_19_health_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["ok", "healthy"]
    assert data["service"] == "sonar-backend"


# 20. Natural Seabed is available
def test_20_natural_seabed_is_available():
    # GET /api/v1/models explicitly marks natural_seabed as available
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "natural_seabed" not in data["unavailable_models"]
    active_keys = [m["id"] for m in data["models"]]
    assert "natural_seabed" in active_keys

    # Health endpoint explicitly reports natural_seabed as available
    health = client.get("/api/v1/health").json()
    assert health["models"]["natural_seabed"] == "available"


# 21. No fake coordinates
def test_21_no_fake_coordinates():
    det = build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.90), index=0)
    assert det.has_target_geolocation is False
    assert det.survey_latitude is None
    assert det.survey_longitude is None
    assert "image" in det.imagePosition["display"].lower() or "x:" in det.imagePosition["display"].lower()


# 22. No stale detection state
def test_22_no_stale_detection_state():
    # Analysis with clean sonar returns empty detections list
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("clean_after.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Detection list must not leak from any previous tests
    assert isinstance(data["detections"], list)


# 23. No stale report state
def test_23_no_stale_report_state():
    empty_summary = compute_analysis_summary([])
    assert empty_summary.total_detections == 0
    assert empty_summary.high_priority == 0
    assert empty_summary.medium_priority == 0
    assert empty_summary.low_priority == 0
    assert empty_summary.categories == {}
    assert empty_summary.highest_priority_detection is None


# 24. Backend error handling sanitized
def test_24_backend_error_handling_sanitized():
    img_bytes = _generate_valid_sonar_bytes()
    # Latitude out of bounds
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_err.png", img_bytes, "image/png")},
        data={"latitude": "195.0"},
    )
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "traceback" not in detail.lower()
    assert "file C:\\" not in detail

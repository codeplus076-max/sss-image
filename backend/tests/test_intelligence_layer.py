"""
Step 8 — SIH26057 Intelligence, Priority & Review Layer Test Suite.

Comprehensive verification of:
1. Priority mapping for every normalized class
2. Priority reason generation
3. Confidence remains separate from priority
4. Default review status (PENDING REVIEW)
5. Evidence status (AVAILABLE / NOT AVAILABLE)
6. Analysis summary counts (total_detections, high, medium, low)
7. Category counts
8. High/medium/low counts accuracy
9. Zero-detection summary (all 0, highest_priority_detection: None)
10. Highest-priority detection selection (HIGH > MEDIUM > LOW)
11. Highest-priority tie-breaking by confidence
12. Multi-model summary aggregation
13. Deduplicated detection count integrity
14. Model provenance preservation
15. No fake values / scientific honesty (no confirmed mine claims, no arbitrary risk formulas)
16. Existing GIS metadata remains correct
17. Existing detection schema backward compatibility
18. Existing random-image rejection still works (422)
19. Existing evidence isolation still works
20. Existing analysis A/B isolation still works
"""

import io
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
    PRIORITY_RULES,
)

client = TestClient(app)
client.post("/api/v1/session")


def _generate_valid_sonar_bytes(w=256, h=256):
    """Generate synthetic valid sonar swath bytes."""
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


# 1. Priority mapping for every normalized class
def test_priority_mapping_for_every_normalized_class():
    test_cases = [
        ("MILCO", "HIGH"),
        ("Mine-Like Contact", "HIGH"),
        ("NOMBO", "HIGH"),
        ("Non-Mine Mine-Like Bottom Object", "HIGH"),
        ("Shipwreck", "HIGH"),
        ("Subsea Pipeline", "MEDIUM"),
        ("Pipeline", "MEDIUM"),
        ("Ghost Gear / Crab Pot", "MEDIUM"),
        ("Ghost Gear", "MEDIUM"),
        ("Crab-Pot", "MEDIUM"),
        ("Cylinder", "LOW"),
        ("Unknown / Unlabeled Artifact", "LOW"),
        ("Class_0", "LOW"),
    ]
    for cls_name, expected_priority in test_cases:
        p, _ = determine_detection_priority(cls_name)
        assert p == expected_priority, f"Class {cls_name} expected {expected_priority}, got {p}"


# 2. Priority reason generation
def test_priority_reason_generation():
    test_cases = [
        ("MILCO", "Mine-like contact requires operator review."),
        ("NOMBO", "Non-mine mine-like bottom object requires operator review."),
        ("Shipwreck", "Shipwreck detected; operator review recommended."),
        ("Pipeline", "Subsea pipeline detected; infrastructure review recommended."),
        ("Crab-Pot", "Ghost gear detected; environmental/operational review recommended."),
        ("Cylinder", "Cylinder detected; review based on survey context."),
        ("Class_0", "Unlabeled artifact requires contextual review."),
    ]
    for raw_cls, expected_sub in test_cases:
        _, reason = determine_detection_priority(raw_cls)
        assert reason == expected_sub, f"Expected '{expected_sub}', got '{reason}'"
        # Scientific honesty check: must never claim confirmed threat or confirmed mine
        assert "confirmed mine" not in reason.lower()
        assert "threat" not in reason.lower()
        assert "dangerous" not in reason.lower()


# 3. Confidence remains separate from priority
def test_confidence_remains_separate_from_priority():
    # Very low confidence MILCO is still HIGH priority
    p_low_conf, _ = determine_detection_priority("MILCO")
    assert p_low_conf == "HIGH"

    # Very high confidence Cylinder is still LOW priority
    p_high_conf, _ = determine_detection_priority("Cylinder")
    assert p_high_conf == "LOW"

    # Build AnalysisDetection instances and verify confidence and priority are distinct fields
    det1 = build_analysis_detection(
        det=_make_det(model_name="mine_detector", raw_class="MILCO", conf=0.15),
        index=0,
        image_width=100,
        image_height=100,
    )
    assert det1.confidence == 0.15
    assert det1.priority == "HIGH"
    assert det1.confidence_percent == 15.0

    det2 = build_analysis_detection(
        det=_make_det(model_name="cylinder", raw_class="Cylinder", conf=0.99),
        index=1,
        image_width=100,
        image_height=100,
    )
    assert det2.confidence == 0.99
    assert det2.priority == "LOW"
    assert det2.confidence_percent == 99.0


# 4. Default review status
def test_default_review_status():
    det = build_analysis_detection(
        det=_make_det(model_name="mine_detector", raw_class="MILCO", conf=0.88),
        index=0,
        image_width=100,
        image_height=100,
    )
    assert det.review_status == "PENDING REVIEW"
    assert det.intelligence.review_status == "PENDING REVIEW"
    # Never claim human reviewed
    assert det.review_status != "REVIEWED"


# 5. Evidence status
def test_evidence_status():
    det_avail = build_analysis_detection(
        det=_make_det(model_name="shipwreck", raw_class="Shipwreck", conf=0.92),
        index=0,
        image_width=100,
        image_height=100,
        evidence_available=True,
    )
    assert det_avail.evidence_status == "AVAILABLE"
    assert det_avail.intelligence.evidence_status == "AVAILABLE"

    det_not_avail = build_analysis_detection(
        det=_make_det(model_name="shipwreck", raw_class="Shipwreck", conf=0.92),
        index=0,
        image_width=100,
        image_height=100,
        evidence_available=False,
    )
    assert det_not_avail.evidence_status == "NOT AVAILABLE"
    assert det_not_avail.intelligence.evidence_status == "NOT AVAILABLE"


# 6. Analysis summary counts
def test_analysis_summary_counts():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0, image_width=100, image_height=100),
        build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.75), index=1, image_width=100, image_height=100),
        build_analysis_detection(_make_det("subpipes", "Pipeline", 0.80), index=2, image_width=100, image_height=100),
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.90), index=3, image_width=100, image_height=100),
    ]
    summary = compute_analysis_summary(dets)
    assert summary.total_detections == 4
    assert summary.high_priority == 2
    assert summary.medium_priority == 1
    assert summary.low_priority == 1
    assert summary.high_priority + summary.medium_priority + summary.low_priority == summary.total_detections


# 7. Category counts
def test_category_counts():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0, image_width=100, image_height=100),
        build_analysis_detection(_make_det("mine_detector", "NOMBO", 0.70), index=1, image_width=100, image_height=100),
        build_analysis_detection(_make_det("ghostvision", "Crab-Pot", 0.65), index=2, image_width=100, image_height=100),
        build_analysis_detection(_make_det("ghostvision", "Crab-Pot", 0.68), index=3, image_width=100, image_height=100),
    ]
    summary = compute_analysis_summary(dets)
    assert summary.categories.get("Mine-Like Contact") == 1
    assert summary.categories.get("Non-Mine Mine-Like Bottom Object") == 1
    assert summary.categories.get("Ghost Gear / Crab Pot") == 2
    assert sum(summary.categories.values()) == 4


# 8. High/medium/low counts accuracy
def test_high_medium_low_counts():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.90), index=0, image_width=100, image_height=100), # HIGH
        build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.85), index=1, image_width=100, image_height=100),   # HIGH
        build_analysis_detection(_make_det("subpipes", "Pipeline", 0.80), index=2, image_width=100, image_height=100),     # MEDIUM
        build_analysis_detection(_make_det("ghostvision", "Crab-Pot", 0.75), index=3, image_width=100, image_height=100), # MEDIUM
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.70), index=4, image_width=100, image_height=100),     # LOW
        build_analysis_detection(_make_det("cylinder", "Class_0", 0.60), index=5, image_width=100, image_height=100),      # LOW
    ]
    summary = compute_analysis_summary(dets)
    assert summary.high_priority == 2
    assert summary.medium_priority == 2
    assert summary.low_priority == 2


# 9. Zero-detection summary
def test_zero_detection_summary():
    summary = compute_analysis_summary([])
    assert summary.total_detections == 0
    assert summary.high_priority == 0
    assert summary.medium_priority == 0
    assert summary.low_priority == 0
    assert summary.categories == {}
    assert summary.highest_priority_detection is None


# 10. Highest-priority detection selection (HIGH > MEDIUM > LOW)
def test_highest_priority_detection_selection():
    dets = [
        # Even with lower confidence (0.45), HIGH beats MEDIUM with 0.95
        build_analysis_detection(_make_det("subpipes", "Pipeline", 0.95), index=0, image_width=100, image_height=100), # MEDIUM
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.99), index=1, image_width=100, image_height=100), # LOW
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.45), index=2, image_width=100, image_height=100), # HIGH
    ]
    highest = get_highest_priority_detection(dets)
    assert highest is not None
    assert highest.priority == "HIGH"
    assert highest.display_class == "Mine-Like Contact"
    assert highest.confidence == 0.45


# 11. Highest-priority tie-breaking by confidence
def test_highest_priority_tie_breaking_by_confidence():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.82), index=0, image_width=100, image_height=100), # HIGH 0.82
        build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.94), index=1, image_width=100, image_height=100), # HIGH 0.94
        build_analysis_detection(_make_det("mine_detector", "NOMBO", 0.88), index=2, image_width=100, image_height=100), # HIGH 0.88
    ]
    highest = get_highest_priority_detection(dets)
    assert highest is not None
    assert highest.priority == "HIGH"
    assert highest.display_class == "Shipwreck"
    assert highest.confidence == 0.94


# 12. Multi-model summary
def test_multi_model_summary():
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0, image_width=100, image_height=100),
        build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.88), index=1, image_width=100, image_height=100),
        build_analysis_detection(_make_det("ghostvision", "Crab-Pot", 0.78), index=2, image_width=100, image_height=100),
        build_analysis_detection(_make_det("subpipes", "Pipeline", 0.82), index=3, image_width=100, image_height=100),
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.72), index=4, image_width=100, image_height=100),
    ]
    summary = compute_analysis_summary(dets)
    assert summary.total_detections == 5
    assert summary.high_priority == 2
    assert summary.medium_priority == 2
    assert summary.low_priority == 1
    assert len(summary.categories) == 5


# 13. Deduplicated detection count
def test_deduplicated_detection_count():
    # If 2 detections exist post-deduplication, summary count must be exactly 2
    dets = [
        build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0, image_width=100, image_height=100),
        build_analysis_detection(_make_det("cylinder", "Cylinder", 0.90), index=1, image_width=100, image_height=100),
    ]
    summary = compute_analysis_summary(dets)
    assert summary.total_detections == 2
    assert sum(summary.categories.values()) == 2


# 14. Model provenance
def test_model_provenance():
    det1 = build_analysis_detection(_make_det("mine_detector", "MILCO", 0.85), index=0, image_width=100, image_height=100)
    assert det1.model == "mine_detector"
    assert det1.raw_class == "MILCO"

    det2 = build_analysis_detection(_make_det("shipwreck", "Shipwreck", 0.92), index=1, image_width=100, image_height=100)
    assert det2.model == "shipwreck"
    assert det2.raw_class == "Shipwreck"


# 15. No fake values / scientific honesty
def test_no_fake_values():
    # Without geolocation
    det_nogeo = build_analysis_detection(
        det=_make_det("mine_detector", "MILCO", 0.89),
        index=0,
        image_width=100,
        image_height=100,
    )
    assert det_nogeo.has_target_geolocation is False
    assert "no survey navigation metadata" in det_nogeo.target_geolocation_note.lower()
    assert det_nogeo.priority in ["HIGH", "MEDIUM", "LOW"]
    assert "operator review" in det_nogeo.priority_reason.lower()

    # With survey geolocation anchor
    geo = AnalysisGeolocation(latitude=18.9175, longitude=72.8375, geolocation_available=True)
    det_geo = build_analysis_detection(
        det=_make_det("mine_detector", "MILCO", 0.89),
        index=0,
        image_width=100,
        image_height=100,
        geolocation=geo,
    )
    assert det_geo.has_target_geolocation is False
    assert "image-space" in det_geo.target_geolocation_note.lower()
    assert det_geo.survey_latitude == 18.9175
    assert det_geo.survey_longitude == 72.8375


# 16. Existing GIS metadata remains correct
def test_existing_gis_metadata_remains_correct():
    det_res = _make_det("shipwreck", "Shipwreck", 0.90)
    geo = AnalysisGeolocation(latitude=15.4989, longitude=73.8278, geolocation_available=True)
    det = build_analysis_detection(det_res, index=0, image_width=100, image_height=100, geolocation=geo)
    assert det.survey_latitude == 15.4989
    assert det.survey_longitude == 73.8278
    assert "EPSG:4326" in det.coordinateReference
    assert "WGS 84" in det.coordinateReference
    assert det.has_target_geolocation is False
    assert "image-space" in det.target_geolocation_note.lower()

    # Also check endpoint metadata
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_gis.png", img_bytes, "image/png")},
        data={"latitude": "15.4989", "longitude": "73.8278", "depth": "22.5"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["geolocation_available"] is True
    assert abs(data["metadata"]["latitude"] - 15.4989) < 0.0001
    assert abs(data["metadata"]["longitude"] - 73.8278) < 0.0001


# 17. Existing detection schema remains backward compatible
def test_existing_detection_schema_backward_compatibility():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_schema.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Core response fields preserved
    assert "analysis_id" in data
    assert "status" in data
    assert "summary" in data
    assert "detections" in data
    assert "metadata" in data
    assert "geolocation" in data

    # Summary has new intelligence fields while maintaining compatibility
    summary = data["summary"]
    assert "total_detections" in summary
    assert "high_priority" in summary
    assert "medium_priority" in summary
    assert "low_priority" in summary
    assert "categories" in summary

    # If any detections, verify legacy + intelligence fields
    for det in data["detections"]:
        assert "model" in det
        assert "raw_class" in det
        assert "display_class" in det
        assert "confidence" in det
        assert "confidence_percent" in det
        assert "bbox" in det
        assert "imagePosition" in det
        assert "priority" in det
        assert "priority_reason" in det
        assert "review_status" in det
        assert "evidence_status" in det
        assert "intelligence" in det
        assert det["intelligence"]["priority"] == det["priority"]


# 18. Existing random-image rejection still works
def test_existing_random_image_rejection():
    # Random RGB image should be rejected at gate
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb[:85, :, 0] = 255
    rgb[85:170, :, 1] = 255
    rgb[170:, :, 2] = 255
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG")
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("random.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert resp.status_code == 422
    assert resp.json().get("error") == "INVALID_SONAR_IMAGE"


# 19. Existing evidence isolation still works
def test_existing_evidence_isolation():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_ev.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    analysis_id = resp.json()["analysis_id"]

    ev_resp = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert ev_resp.status_code == 200
    assert ev_resp.headers["content-type"] == "image/png"

    # Nonexistent analysis returns 404
    non_existent = client.get("/api/v1/analysis/non-existent-analysis-id/evidence")
    assert non_existent.status_code == 404


# 20. Existing analysis A/B isolation still works
def test_existing_analysis_ab_isolation():
    img_bytes_a = _generate_valid_sonar_bytes()
    img_bytes_b = _generate_valid_sonar_bytes()

    resp_a = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_a.png", img_bytes_a, "image/png")},
        data={"latitude": "12.34", "longitude": "56.78"},
    )
    resp_b = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_b.png", img_bytes_b, "image/png")},
        data={"latitude": "23.45", "longitude": "67.89"},
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    data_a = resp_a.json()
    data_b = resp_b.json()

    assert data_a["analysis_id"] != data_b["analysis_id"]
    assert abs(data_a["metadata"]["latitude"] - 12.34) < 0.0001
    assert abs(data_b["metadata"]["latitude"] - 23.45) < 0.0001

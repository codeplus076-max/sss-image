"""
Step 6 — Detection & Evidence Quality Audit Tests.

Verifies:
1. Detection schema consistency.
2. Valid bbox coordinates.
3. Invalid bbox rejection/handling.
4. Confidence range.
5. Confidence frontend conversion.
6. Model provenance.
7. Class normalization.
8. Unknown Class_0 handling.
9. Evidence belongs to correct analysis.
10. Analysis A/B isolation.
11. Zero-detection analysis.
12. Overlapping MILCO/NOMBO model behavior (deduplication).
13. Multiple-model analysis.
14. Existing random-image rejection.
15. Existing geolocation behaviour.
"""

import io
import json
import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.main import app
from app.schemas.inference import BoundingBox, DetectionResult
from app.services.detection_normalizer import (
    build_analysis_detection,
    calculate_iou,
    deduplicate_cross_model_detections,
    get_category_name,
    normalize_class_name,
)
from app.services.analysis_service import analysis_service

client = TestClient(app)


def _generate_valid_sonar_bytes(w=256, h=256):
    """Generate synthetic valid sonar swath bytes."""
    noise = np.random.normal(loc=35, scale=6, size=(h, w)).clip(5, 100).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buf, format="PNG")
    return buf.getvalue()


# 1. Detection schema consistency
def test_detection_schema_consistency():
    det_res = DetectionResult(
        model_name="cylinder",
        class_id=0,
        raw_class_name="Cylinder",
        semantic_class_name="Cylinder",
        confidence=0.885,
        bounding_box=BoundingBox(
            x1=10.0, y1=20.0, x2=50.0, y2=80.0,
            width=40.0, height=60.0,
            norm_x1=0.1, norm_y1=0.2, norm_w=0.4, norm_h=0.6
        ),
        image_width=100,
        image_height=100,
    )
    analysis_det = build_analysis_detection(det_res, index=0, image_width=100, image_height=100)
    
    assert analysis_det.id == "DET-01"
    assert analysis_det.model == "cylinder"
    assert analysis_det.raw_class == "Cylinder"
    assert analysis_det.display_class == "Cylinder"
    assert analysis_det.category == "Cylinder"
    assert analysis_det.confidence == 0.885
    assert analysis_det.confidence_percent == 88.5
    assert analysis_det.bbox.x1 == 10.0
    assert analysis_det.bbox.y1 == 20.0
    assert analysis_det.bbox.x2 == 50.0
    assert analysis_det.bbox.y2 == 80.0
    assert analysis_det.bbox.x == 10.0
    assert analysis_det.bbox.y == 20.0


# 2. Valid bbox coordinates (x1 < x2, y1 < y2, bounded)
def test_valid_bbox_coordinates():
    det_res = DetectionResult(
        model_name="subpipes",
        class_id=0,
        raw_class_name="Pipeline",
        semantic_class_name="Subsea Pipeline",
        confidence=0.91,
        bounding_box=BoundingBox(
            x1=25.0, y1=30.0, x2=150.0, y2=200.0,
            width=125.0, height=170.0,
            norm_x1=0.125, norm_y1=0.15, norm_w=0.625, norm_h=0.85
        ),
        image_width=200,
        image_height=200,
    )
    det = build_analysis_detection(det_res, index=1, image_width=200, image_height=200)
    assert det.bbox.x1 < det.bbox.x2
    assert det.bbox.y1 < det.bbox.y2
    assert 0.0 <= det.bbox.x1 <= 200.0
    assert 0.0 <= det.bbox.x2 <= 200.0
    assert 0.0 <= det.bbox.y1 <= 200.0
    assert 0.0 <= det.bbox.y2 <= 200.0


# 3. Invalid bbox rejection/handling (inversion and boundary overflow handled safely)
def test_invalid_bbox_coordinate_handling():
    # Inverted box where x1 > x2 and y1 > y2, with out-of-bounds coords
    det_res = DetectionResult(
        model_name="ghostvision",
        class_id=0,
        raw_class_name="Crab-Pot",
        semantic_class_name="Ghost Gear",
        confidence=0.75,
        bounding_box=BoundingBox(
            x1=350.0, y1=450.0, x2=-50.0, y2=-10.0,
            width=400.0, height=460.0,
            norm_x1=1.0, norm_y1=1.0, norm_w=1.0, norm_h=1.0
        ),
        image_width=200,
        image_height=200,
    )
    det = build_analysis_detection(det_res, index=0, image_width=200, image_height=200)
    assert det.bbox.x1 <= det.bbox.x2
    assert det.bbox.y1 <= det.bbox.y2
    assert det.bbox.x1 == 0.0
    assert det.bbox.x2 == 200.0
    assert det.bbox.y1 == 0.0
    assert det.bbox.y2 == 200.0


# 4. Confidence range (enforced between 0.0 and 1.0)
def test_confidence_range_enforcement():
    # Out of range confidence is clamped to [0.0, 1.0]
    det_res_high = DetectionResult(
        model_name="mine_detector",
        class_id=0,
        raw_class_name="MILCO",
        semantic_class_name="Mine-Like Contact",
        confidence=1.45,
        bounding_box=BoundingBox(x1=10, y1=10, x2=20, y2=20, width=10, height=10, norm_x1=0.1, norm_y1=0.1, norm_w=0.1, norm_h=0.1),
        image_width=100,
        image_height=100,
    )
    det = build_analysis_detection(det_res_high, index=0, image_width=100, image_height=100)
    assert 0.0 <= det.confidence <= 1.0
    assert det.confidence == 1.0
    assert det.confidence_percent == 100.0


# 5. Confidence frontend conversion
def test_confidence_frontend_conversion():
    det_res = DetectionResult(
        model_name="shipwreck",
        class_id=0,
        raw_class_name="Shipwreck",
        semantic_class_name="Shipwreck",
        confidence=0.827,
        bounding_box=BoundingBox(x1=10, y1=10, x2=50, y2=50, width=40, height=40, norm_x1=0.1, norm_y1=0.1, norm_w=0.4, norm_h=0.4),
        image_width=100,
        image_height=100,
    )
    det = build_analysis_detection(det_res, index=0, image_width=100, image_height=100)
    assert det.confidence == 0.827
    assert det.confidence_percent == 82.7


# 6. Model provenance
def test_model_provenance_preservation():
    det_res = DetectionResult(
        model_name="shipwreck",
        class_id=1,
        raw_class_name="MILCO",
        semantic_class_name="Mine-Like Contact",
        confidence=0.912,
        bounding_box=BoundingBox(x1=10, y1=10, x2=30, y2=30, width=20, height=20, norm_x1=0.1, norm_y1=0.1, norm_w=0.2, norm_h=0.2),
        image_width=100,
        image_height=100,
    )
    det = build_analysis_detection(det_res, index=0, image_width=100, image_height=100)
    assert det.model == "shipwreck"
    assert det.raw_class == "MILCO"
    assert det.display_class == "Mine-Like Contact"


# 7. Class normalization
def test_class_normalization_mappings():
    assert normalize_class_name("Cylinder") == "Cylinder"
    assert normalize_class_name("Crab-Pot") == "Ghost Gear"
    assert normalize_class_name("Pipeline") == "Subsea Pipeline"
    assert normalize_class_name("Shipwreck") == "Shipwreck"
    assert normalize_class_name("MILCO") == "Mine-Like Contact"
    assert normalize_class_name("NOMBO") == "Non-Mine Mine-Like Bottom Object"


# 8. Unknown Class_0 handling
def test_unknown_class_0_handling():
    assert normalize_class_name("Class_0") == "Class_0 (Unknown / Unlabeled)"
    assert get_category_name("Class_0") == "Unknown / Unlabeled Artifact"


# 9. Evidence belongs to correct analysis
def test_evidence_belongs_to_correct_analysis():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_ev.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    analysis_id = data["analysis_id"]

    ev_resp = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
    assert ev_resp.status_code == 200
    assert ev_resp.content == img_bytes
    assert "survey_ev.png" in ev_resp.headers.get("content-disposition", "")


# 10. Analysis A/B isolation
def test_analysis_ab_isolation():
    img_bytes_a = _generate_valid_sonar_bytes(200, 200)
    img_bytes_b = _generate_valid_sonar_bytes(300, 300)

    resp_a = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_a.png", img_bytes_a, "image/png")},
        data={"latitude": "12.34", "longitude": "56.78"},
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    id_a = data_a["analysis_id"]

    resp_b = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("survey_b.png", img_bytes_b, "image/png")},
        data={"latitude": "88.11", "longitude": "-44.22"},
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    id_b = data_b["analysis_id"]

    # Verify Analysis A record
    rec_a = client.get(f"/api/v1/analysis/{id_a}").json()
    assert rec_a["analysis_id"] == id_a
    assert abs(rec_a["metadata"]["latitude"] - 12.34) < 0.001
    assert abs(rec_a["metadata"]["longitude"] - 56.78) < 0.001
    assert rec_a["image"]["filename"] == "survey_a.png"

    # Verify Analysis B record
    rec_b = client.get(f"/api/v1/analysis/{id_b}").json()
    assert rec_b["analysis_id"] == id_b
    assert abs(rec_b["metadata"]["latitude"] - 88.11) < 0.001
    assert abs(rec_b["metadata"]["longitude"] - (-44.22)) < 0.001
    assert rec_b["image"]["filename"] == "survey_b.png"

    # Verify Evidence A vs B
    ev_a = client.get(f"/api/v1/analysis/{id_a}/evidence").content
    ev_b = client.get(f"/api/v1/analysis/{id_b}/evidence").content
    assert ev_a == img_bytes_a
    assert ev_b == img_bytes_b
    assert ev_a != ev_b


# 11. Zero-detection analysis
def test_zero_detection_analysis_success():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("zero_det.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"].upper() == "COMPLETED"
    assert "summary" in data
    assert isinstance(data["detections"], list)


# 12. Overlapping MILCO/NOMBO model behavior (deduplication)
def test_overlapping_milco_deduplication():
    # Two detections of MILCO at the exact same location from mines and shipwreck
    det_mines = DetectionResult(
        model_name="mine_detector",
        class_id=0,
        raw_class_name="MILCO",
        semantic_class_name="Mine-Like Contact",
        confidence=0.85,
        bounding_box=BoundingBox(x1=50, y1=50, x2=100, y2=100, width=50, height=50, norm_x1=0.25, norm_y1=0.25, norm_w=0.25, norm_h=0.25),
        image_width=200,
        image_height=200,
    )
    det_shipwreck = DetectionResult(
        model_name="shipwreck",
        class_id=1,
        raw_class_name="MILCO",
        semantic_class_name="Mine-Like Contact",
        confidence=0.70,
        bounding_box=BoundingBox(x1=52, y1=48, x2=101, y2=99, width=49, height=51, norm_x1=0.26, norm_y1=0.24, norm_w=0.245, norm_h=0.255),
        image_width=200,
        image_height=200,
    )
    # Different class at same location (e.g. Shipwreck)
    det_other = DetectionResult(
        model_name="shipwreck",
        class_id=2,
        raw_class_name="Shipwreck",
        semantic_class_name="Shipwreck",
        confidence=0.65,
        bounding_box=BoundingBox(x1=50, y1=50, x2=100, y2=100, width=50, height=50, norm_x1=0.25, norm_y1=0.25, norm_w=0.25, norm_h=0.25),
        image_width=200,
        image_height=200,
    )

    deduped = deduplicate_cross_model_detections([det_mines, det_shipwreck, det_other])
    # Cross-model spatial clustering designates the highest-confidence prediction (0.85 MILCO)
    # as the primary winner on canvas, preserving secondary overlapping predictions as competing hypotheses!
    assert len(deduped) == 1
    primary = deduped[0]
    assert primary.confidence == 0.85
    assert primary.model_name == "mine_detector"
    assert primary.raw_class_name == "MILCO"
    assert len(primary.competing_hypotheses) >= 1
    competing_classes = [h.get("raw_class") or h.get("raw_class_name") for h in primary.competing_hypotheses]
    assert "Shipwreck" in competing_classes or "MILCO" in competing_classes


# 13. Multiple-model analysis
def test_multiple_model_analysis_execution():
    img_bytes = _generate_valid_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("multimodel.png", img_bytes, "image/png")},
        data={"selected_models": "cylinder,ghostvision,subpipes", "enable_seabed_gate": "false"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cylinder" in data["summary"]["models_executed"]
    assert "ghostvision" in data["summary"]["models_executed"]
    assert "subpipes" in data["summary"]["models_executed"]


# 14. Existing random-image rejection
def test_existing_random_image_rejection_preserved():
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
    data = resp.json()
    assert data.get("error") == "INVALID_SONAR_IMAGE"


# 15. Existing geolocation behaviour
def test_existing_geolocation_behaviour_preserved():
    img_bytes = _generate_valid_sonar_bytes()
    # Test with geolocation
    resp_geo = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("geo.png", img_bytes, "image/png")},
        data={"latitude": "15.5", "longitude": "73.8", "depth": "25.0", "heading": "90.0"},
    )
    assert resp_geo.status_code == 200
    meta_geo = resp_geo.json()["metadata"]
    assert meta_geo["geolocation_available"] is True
    assert abs(meta_geo["latitude"] - 15.5) < 0.001
    assert abs(meta_geo["longitude"] - 73.8) < 0.001

    # Test without geolocation
    resp_nogeo = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("nogeo.png", img_bytes, "image/png")},
    )
    assert resp_nogeo.status_code == 200
    meta_nogeo = resp_nogeo.json()["metadata"]
    assert meta_nogeo["geolocation_available"] is False
    assert meta_nogeo["latitude"] is None
    assert meta_nogeo["longitude"] is None

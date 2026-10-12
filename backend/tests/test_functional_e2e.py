"""
Step 4 E2E Functional Integration Verification Tests (TEST A through TEST E).
"""
import io
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
client.post("/api/v1/session")
SAMPLE_SONAR_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "assets" / "underwater_plate_final.jpg"

def _load_sonar_bytes():
    if SAMPLE_SONAR_PATH.exists():
        with open(SAMPLE_SONAR_PATH, "rb") as f:
            return f.read()
    # Fallback to realistic synthetic sonar swath if file not found
    arr = np.random.normal(loc=40, scale=12, size=(300, 300)).clip(0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="JPEG")
    return buf.getvalue()

def test_a_valid_sonar_sample():
    """TEST A: Valid real sonar sample upload succeeds, backend runs inference, returns results."""
    sonar_bytes = _load_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("underwater_plate_final.jpg", sonar_bytes, "image/jpeg")},
        data={"selected_models": "shipwreck"}
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res.get("status") in ("COMPLETED", "completed")
    assert "analysis_id" in res
    assert "summary" in res
    assert "detections" in res
    print(f"\n[TEST A PASS] ID: {res.get('analysis_id')}, Detections: {len(res.get('detections'))}")

def test_b_random_photograph_rejected():
    """TEST B: Random polychromatic photograph returns HTTP 422 with INVALID_SONAR_IMAGE."""
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb[:85, :, 0] = 255   # Red
    rgb[85:170, :, 1] = 255 # Green
    rgb[170:, :, 2] = 255  # Blue
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG")
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("flower_photo.jpg", buf.getvalue(), "image/jpeg")}
    )
    assert resp.status_code == 422
    err_body = resp.json()
    assert err_body.get("error") == "INVALID_SONAR_IMAGE"
    print(f"\n[TEST B PASS] HTTP 422 rejection: {err_body.get('error')}")

def test_c_sonar_with_geolocation():
    """TEST C: Valid sonar with latitude/longitude persists real coordinates."""
    sonar_bytes = _load_sonar_bytes()
    fields = {"latitude": "18.9175", "longitude": "72.8375", "depth": "45.0", "heading": "135.0"}
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_geo.jpg", sonar_bytes, "image/jpeg")},
        data=fields
    )
    assert resp.status_code == 200
    res = resp.json()
    meta = res.get("metadata", {})
    assert meta.get("geolocation_available") is True
    assert abs(meta.get("latitude") - 18.9175) < 0.001
    assert abs(meta.get("longitude") - 72.8375) < 0.001
    print(f"\n[TEST C PASS] Geolocation persisted: {meta.get('latitude')}, {meta.get('longitude')}")

def test_d_sonar_without_geolocation():
    """TEST D: Valid sonar without coordinates indicates geolocation is unavailable (not invented)."""
    sonar_bytes = _load_sonar_bytes()
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("sonar_nogeo.jpg", sonar_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200
    res = resp.json()
    meta = res.get("metadata", {})
    assert meta.get("geolocation_available") is False
    assert meta.get("latitude") is None
    assert meta.get("longitude") is None
    print("\n[TEST D PASS] Geolocation correctly flagged unavailable without invented coords")

def test_e_zero_detections():
    """TEST E: Valid sonar swath with zero detections returns HTTP 200 without error."""
    noise = np.random.normal(loc=35, scale=6, size=(512, 512)).clip(5, 100).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buf, format="PNG")
    resp = client.post(
        "/api/v1/analysis/analyze",
        files={"image": ("clear_water.png", buf.getvalue(), "image/png")},
        data={"selected_models": "shipwreck"}
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res.get("summary", {}).get("total_detections") == 0
    print("\n[TEST E PASS] HTTP 200 with total_detections = 0 successfully counted")


"""Evaluation script to test real dataset images through the app's AnalysisService.

Evaluates:
- Naval Mines (MILCO / NOMBO)
- Shipwrecks (Shipwreck / Hull)
- Cylinders & Containers
- Clean Natural Seabed (Seabed texture)
"""

import os
import sys
import time
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["USE_REMOTE_INFERENCE"] = "false"

from app.services.analysis_service import AnalysisService

DATASET_DIR = backend_dir.parent / "test_datasets"

def evaluate_subset(sample_limit_per_cat=5):
    categories = [
        ("01_naval_mines", ["Mine-Like Contact", "Non-Mine Mine-Like Bottom Object", "MILCO", "NOMBO", "Class_0", "Acoustic Anomaly"]),
        ("02_shipwrecks", ["Shipwreck", "Maritime Shipwreck / Hull", "Acoustic Anomaly", "Acoustic Contrast", "Class_0", "Cylinder"]),
        ("03_cylinders_and_containers", ["Cylinder", "Industrial Cylinder / Drum", "Non-Mine Mine-Like Bottom Object", "NOMBO"]),
        ("04_clean_natural_seabed", []),  # Expect 0 detections or clean seabed
    ]

    results = []

    def log(msg=""):
        print(msg, flush=True)

    log("=" * 80)
    log("STARTING STRICT DATASET PIPELINE EVALUATION")
    log("=" * 80)

    for cat_name, expected_classes in categories:
        cat_path = DATASET_DIR / cat_name
        if not cat_path.exists():
            log(f"Skipping {cat_name}: not found")
            continue

        images = sorted(list(cat_path.glob("*.png")) + list(cat_path.glob("*.jpg")))[:sample_limit_per_cat]
        log(f"\nEvaluating Category: {cat_name} ({len(images)} images)")
        log("-" * 80)

        for img_path in images:
            t0 = time.time()
            with open(img_path, "rb") as f:
                img_bytes = f.read()

            try:
                resp = AnalysisService.analyze_sonar_image(
                    file_bytes=img_bytes,
                    filename=img_path.name,
                    enable_seabed_gate=False,
                    enable_roi_reverify=True,
                    roi_clean_threshold=0.70,
                )
                dur = time.time() - t0
                det_count = len(resp.detections)
                det_summary = [
                    f"{d.display_class} ({round(d.confidence_percent, 1)}%) [model:{d.model}]"
                    for d in resp.detections
                ]

                # Strict correctness check:
                is_clean_expected = (len(expected_classes) == 0)
                if is_clean_expected:
                    # Clean seabed expected: 0 detections is PASS, any detection is FALSE POSITIVE
                    passed = (det_count == 0)
                    status = "PASS (CLEAN)" if passed else f"FAIL (FALSE ALARM: {det_summary})"
                else:
                    # Target expected: at least one detection matching expected class is PASS
                    matched = any(
                        any(exp.lower() in d.display_class.lower() or exp.lower() in (d.raw_class or "").lower() for exp in expected_classes)
                        for d in resp.detections
                    )
                    passed = matched
                    status = "PASS" if passed else (f"FAIL (MISCLASSIFIED: {det_summary})" if det_count > 0 else "FAIL (MISSED TARGET)")

                log(f"[{status}] {img_path.name} | {det_count} det | {dur:.2f}s | {det_summary}")

                results.append({
                    "category": cat_name,
                    "filename": img_path.name,
                    "passed": passed,
                    "det_count": det_count,
                    "detections": det_summary,
                    "status": status,
                    "time_s": dur,
                })

            except Exception as e:
                log(f"[ERROR] {img_path.name}: {e}")
                results.append({
                    "category": cat_name,
                    "filename": img_path.name,
                    "passed": False,
                    "error": str(e),
                })

    # Summary Statistics
    log("\n" + "=" * 80)
    log("EVALUATION SUMMARY REPORT")
    log("=" * 80)
    total = len(results)
    passed_count = sum(1 for r in results if r.get("passed"))
    rate = (passed_count / total * 100) if total else 0
    log(f"Total Evaluated: {total}")
    log(f"Total Passed:    {passed_count} ({rate:.1f}%)")
    log(f"Total Failed:    {total - passed_count}")

    by_cat = {}
    for r in results:
        c = r["category"]
        by_cat.setdefault(c, []).append(r)

    for c, items in by_cat.items():
        c_passed = sum(1 for i in items if i.get("passed"))
        c_rate = (c_passed / len(items) * 100) if items else 0
        log(f"  {c}: {c_passed}/{len(items)} passed ({c_rate:.1f}%)")

if __name__ == "__main__":
    evaluate_subset(sample_limit_per_cat=4)

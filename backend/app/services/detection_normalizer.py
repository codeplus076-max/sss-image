"""Detection Normalizer Service.

Normalizes raw model outputs into standardized Side-Scan Sonar anomaly classes,
calculates bounding box geometries, and computes survey summary statistics.
"""

from typing import Any, Dict, List, Optional, Tuple
from app.schemas.analysis import (
    AlternativeHypothesis,
    AnalysisBoundingBox,
    AnalysisDetection,
    AnalysisGeolocation,
    AnalysisSummary,
    DetectionIntelligence,
    HighestPriorityDetectionSummary,
)
from app.schemas.inference import DetectionResult

# Strict semantic class normalization dictionary per specification
NORMALIZATION_MAP: Dict[str, str] = {
    "Crab-Pot": "Ghost Gear",
    "Pipeline": "Subsea Pipeline",
    "Cylinder": "Cylinder",
    "Shipwreck": "Shipwreck",
    "shipwreck": "Shipwreck",
    "Maritime Shipwreck / Hull": "Shipwreck",
    "MILCO": "Mine-Like Contact",
    "NOMBO": "Non-Mine Mine-Like Bottom Object",
    "Class_0": "Class_0 (Unknown / Unlabeled)",
    "Acoustic Anomaly": "Acoustic Anomaly",
    "Acoustic Contrast Anomaly (Highlight/Shadow)": "Acoustic Anomaly",
}

CATEGORY_MAP: Dict[str, str] = {
    "Crab-Pot": "Ghost Gear / Crab Pot",
    "Pipeline": "Subsea Pipeline",
    "Cylinder": "Cylinder",
    "Shipwreck": "Shipwreck",
    "shipwreck": "Shipwreck",
    "Maritime Shipwreck / Hull": "Shipwreck",
    "MILCO": "Mine-Like Contact",
    "NOMBO": "Non-Mine Mine-Like Bottom Object",
    "Class_0": "Unknown / Unlabeled Artifact",
    "Acoustic Anomaly": "Acoustic Anomaly",
    "Acoustic Contrast Anomaly (Highlight/Shadow)": "Acoustic Anomaly",
}

# Rule-based operator operational review priority mapping
PRIORITY_RULES: Dict[str, Tuple[str, str]] = {
    "MILCO": ("HIGH", "Mine-like contact requires operator review."),
    "Mine-Like Contact": ("HIGH", "Mine-like contact requires operator review."),
    "NOMBO": ("HIGH", "Non-mine mine-like bottom object requires operator review."),
    "Non-Mine Mine-Like Bottom Object": ("HIGH", "Non-mine mine-like bottom object requires operator review."),
    "Shipwreck": ("HIGH", "Shipwreck detected; operator review recommended."),
    "shipwreck": ("HIGH", "Shipwreck detected; operator review recommended."),
    "Maritime Shipwreck / Hull": ("HIGH", "Shipwreck detected; operator review recommended."),
    "Acoustic Anomaly": ("HIGH", "Acoustic contrast anomaly confirmed; operator review recommended."),
    "Acoustic Contrast Anomaly (Highlight/Shadow)": ("HIGH", "Acoustic contrast anomaly confirmed; operator review recommended."),
    "Pipeline": ("MEDIUM", "Subsea pipeline detected; infrastructure review recommended."),
    "Subsea Pipeline": ("MEDIUM", "Subsea pipeline detected; infrastructure review recommended."),
    "Crab-Pot": ("MEDIUM", "Ghost gear detected; environmental/operational review recommended."),
    "Ghost Gear": ("MEDIUM", "Ghost gear detected; environmental/operational review recommended."),
    "Ghost Gear / Crab Pot": ("MEDIUM", "Ghost gear detected; environmental/operational review recommended."),
    "Cylinder": ("LOW", "Cylinder detected; review based on survey context."),
    "Class_0": ("LOW", "Unlabeled artifact requires contextual review."),
    "Class_0 (Unknown / Unlabeled)": ("LOW", "Unlabeled artifact requires contextual review."),
    "Unknown / Unlabeled Artifact": ("LOW", "Unlabeled artifact requires contextual review."),
}

PRIORITY_RANKS: Dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def normalize_class_name(raw_class: str) -> str:
    """Map raw model class name to authorized frontend display category."""
    if raw_class in NORMALIZATION_MAP:
        return NORMALIZATION_MAP[raw_class]

    for k, v in NORMALIZATION_MAP.items():
        if k.lower() == raw_class.lower():
            return v

    return raw_class


def get_category_name(raw_class: str) -> str:
    """Map raw model class to canonical high-level category string."""
    if raw_class in CATEGORY_MAP:
        return CATEGORY_MAP[raw_class]

    for k, v in CATEGORY_MAP.items():
        if k.lower() == raw_class.lower():
            return v

    return normalize_class_name(raw_class)


def determine_detection_priority(raw_class: str) -> Tuple[str, str]:
    """Map raw or normalized class to operational review priority and explainable reason."""
    if raw_class in PRIORITY_RULES:
        return PRIORITY_RULES[raw_class]
    for k, v in PRIORITY_RULES.items():
        if k.lower() == raw_class.lower():
            return v
    norm = normalize_class_name(raw_class)
    if norm in PRIORITY_RULES:
        return PRIORITY_RULES[norm]
    for k, v in PRIORITY_RULES.items():
        if k.lower() == norm.lower():
            return v
    return ("LOW", f"{norm} detected; review based on survey context.")


def calculate_iou(box1: Any, box2: Any) -> float:
    """Calculate Intersection-over-Union (IoU) between two bounding boxes."""
    x1 = max(min(box1.x1, box1.x2), min(box2.x1, box2.x2))
    y1 = max(min(box1.y1, box1.y2), min(box2.y1, box2.y2))
    x2 = min(max(box1.x1, box1.x2), max(box2.x1, box2.x2))
    y2 = min(max(box1.y1, box1.y2), max(box2.y1, box2.y2))

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, abs(box1.x2 - box1.x1)) * max(0.0, abs(box1.y2 - box1.y1))
    area2 = max(0.0, abs(box2.x2 - box2.x1)) * max(0.0, abs(box2.y2 - box2.y1))
    union_area = area1 + area2 - inter_area

    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def calculate_edge_distance(box1: BoundingBox, box2: BoundingBox) -> float:
    """Calculate Euclidean distance between closest edges of two bounding boxes (0.0 if overlapping)."""
    import math

    b1_x1, b1_x2 = min(box1.x1, box1.x2), max(box1.x1, box1.x2)
    b1_y1, b1_y2 = min(box1.y1, box1.y2), max(box1.y1, box1.y2)
    b2_x1, b2_x2 = min(box2.x1, box2.x2), max(box2.x1, box2.x2)
    b2_y1, b2_y2 = min(box2.y1, box2.y2), max(box2.y1, box2.y2)

    dx = max(0.0, max(b1_x1, b2_x1) - min(b1_x2, b2_x2))
    dy = max(0.0, max(b1_y1, b2_y1) - min(b1_y2, b2_y2))
    return math.hypot(dx, dy)


def calculate_containment_and_iou(box1: BoundingBox, box2: BoundingBox) -> Tuple[float, float]:
    """Calculate IoU (Intersection over Union) and IoS (Intersection over Smaller Box)."""
    x1 = max(min(box1.x1, box1.x2), min(box2.x1, box2.x2))
    y1 = max(min(box1.y1, box1.y2), min(box2.y1, box2.y2))
    x2 = min(max(box1.x1, box1.x2), max(box2.x1, box2.x2))
    y2 = min(max(box1.y1, box1.y2), max(box2.y1, box2.y2))

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, abs(box1.x2 - box1.x1)) * max(0.0, abs(box1.y2 - box1.y1))
    area2 = max(0.0, abs(box2.x2 - box2.x1)) * max(0.0, abs(box2.y2 - box2.y1))
    min_area = min(area1, area2)
    union_area = area1 + area2 - inter_area

    iou = (inter_area / union_area) if union_area > 0.0 else 0.0
    ios = (inter_area / min_area) if min_area > 0.0 else 0.0
    return iou, ios


def deduplicate_cross_model_detections(
    detections: List[DetectionResult],
    iou_threshold: float = 0.20,
) -> List[DetectionResult]:
    """Cross-model spatial deduplication with multi-hypothesis candidate retention.

    Rules applied:
    - Compare spatial bbox overlap (IoU), containment (IoS), and physical proximity across all candidate detections.
    - When two or more models or candidate detections predict boxes on the same physical contact:
      1. Macro structures (Shipwrecks, Pipelines) with credible confidence (>= 0.35) establish the primary physical contact.
      2. Smaller sub-contacts (e.g. Cylinders or Ordnance) detected on/inside or adjacent to the macro structure
         are absorbed as competing alternative hypotheses.
      3. Multiple candidate boxes on the same anomaly (e.g. fragmented hull sections, adjacent reef tiles)
         are merged into a single clean envelope enclosing the entire anomaly.
      4. Low-confidence background clutter (< 0.35) is suppressed when a dominant confirmed contact (>= 0.50) exists.
      5. Zero messy duplicate boxes on the same physical anomaly.
    """
    if len(detections) <= 1:
        return detections

    def priority_score(d: DetectionResult) -> float:
        score = float(d.confidence)
        raw_lower = (d.raw_class_name or "").lower()

        # Only grant macro footprint precedence if the model has credible confidence (>= 0.35)
        if "shipwreck" in raw_lower and d.confidence >= 0.35:
            score += 0.30
        elif "pipeline" in raw_lower and d.confidence >= 0.35:
            score += 0.20
        elif any(k in raw_lower for k in ["milco", "mine", "nombo"]) and d.confidence >= 0.30:
            score += 0.15

        return score

    sorted_dets = sorted(detections, key=priority_score, reverse=True)
    kept: List[DetectionResult] = []

    for cand in sorted_dets:
        matched_primary = None
        cand_raw = (cand.raw_class_name or "").lower()

        for existing in kept:
            ex_raw = (existing.raw_class_name or "").lower()
            same_class = (
                cand_raw == ex_raw
                or ("shipwreck" in cand_raw and "shipwreck" in ex_raw)
                or ("cylinder" in cand_raw and "cylinder" in ex_raw)
                or ("pipeline" in cand_raw and "pipeline" in ex_raw)
            )

            iou, ios = calculate_containment_and_iou(cand.bounding_box, existing.bounding_box)
            dist = calculate_edge_distance(cand.bounding_box, existing.bounding_box)

            max_dim = max(
                cand.bounding_box.width, cand.bounding_box.height,
                existing.bounding_box.width, existing.bounding_box.height
            )
            has_macro = any(m in ex_raw or m in cand_raw for m in ["shipwreck", "pipeline"])

            # Proximity connection threshold for physical continuity on sonar returns
            if same_class:
                prox_thresh = max(120.0, 0.60 * max_dim)
            elif has_macro:
                # Include sub-targets on hull or trailing in acoustic shadow
                prox_thresh = max(80.0, 0.40 * max_dim)
            else:
                prox_thresh = max(35.0, 0.20 * min(cand.bounding_box.width, existing.bounding_box.width))

            is_overlap = (dist == 0.0 or iou >= 0.10 or ios >= 0.15)
            is_close = (dist <= prox_thresh)

            if is_overlap or is_close:
                matched_primary = existing
                # If same class, expand the primary box envelope to encompass the entire physical anomaly
                if same_class:
                    nx1 = min(existing.bounding_box.x1, cand.bounding_box.x1)
                    ny1 = min(existing.bounding_box.y1, cand.bounding_box.y1)
                    nx2 = max(existing.bounding_box.x2, cand.bounding_box.x2)
                    ny2 = max(existing.bounding_box.y2, cand.bounding_box.y2)
                    existing.bounding_box.x1 = nx1
                    existing.bounding_box.y1 = ny1
                    existing.bounding_box.x2 = nx2
                    existing.bounding_box.y2 = ny2
                    existing.bounding_box.width = max(0.0, nx2 - nx1)
                    existing.bounding_box.height = max(0.0, ny2 - ny1)
                    existing.confidence = max(existing.confidence, cand.confidence)
                break

        if matched_primary is not None:
            # Overlapping or adjacent detection on same contact: record as competing alternative hypothesis
            cand_priority, _ = determine_detection_priority(cand.raw_class_name)
            alt = {
                "model": cand.model_name,
                "raw_class": cand.raw_class_name,
                "display_class": normalize_class_name(cand.raw_class_name),
                "category": get_category_name(cand.raw_class_name),
                "confidence": round(float(cand.confidence), 4),
                "confidence_percent": round(float(cand.confidence) * 100.0, 1),
                "priority": cand_priority,
            }
            if not hasattr(matched_primary, "competing_hypotheses") or matched_primary.competing_hypotheses is None:
                matched_primary.competing_hypotheses = []
            matched_primary.competing_hypotheses.append(alt)
        else:
            if not hasattr(cand, "competing_hypotheses") or cand.competing_hypotheses is None:
                cand.competing_hypotheses = []
            kept.append(cand)

    # Dominant target clutter filter: if top contact >= 0.50, prune faint background noise (< 0.32)
    if kept:
        top_conf = max(float(k.confidence) for k in kept)
        if top_conf >= 0.50:
            kept = [k for k in kept if float(k.confidence) >= 0.32]

    return kept[:3]


def build_analysis_detection(
    result: Optional[DetectionResult] = None,
    index: int = 0,
    image_width: int = 100,
    image_height: int = 100,
    geolocation: Optional[AnalysisGeolocation] = None,
    evidence_available: bool = True,
    det: Optional[DetectionResult] = None,
) -> AnalysisDetection:
    """Transform an internal DetectionResult into a normalized AnalysisDetection with frontend bindings."""
    actual_result = result if result is not None else det
    if actual_result is None:
        raise ValueError("Either result or det must be provided to build_analysis_detection")

    det_id = f"DET-{index + 1:02d}"
    code = f"{index + 1:02d}"
    display_class = normalize_class_name(actual_result.raw_class_name)

    bbox_in = actual_result.bounding_box
    safe_w = max(1, image_width)
    safe_h = max(1, image_height)

    # Validate coordinate ordering (x1 < x2, y1 < y2) and clamp within image boundaries
    x1 = max(0.0, min(float(safe_w), min(bbox_in.x1, bbox_in.x2)))
    x2 = max(0.0, min(float(safe_w), max(bbox_in.x1, bbox_in.x2)))
    y1 = max(0.0, min(float(safe_h), min(bbox_in.y1, bbox_in.y2)))
    y2 = max(0.0, min(float(safe_h), max(bbox_in.y1, bbox_in.y2)))

    box_w = max(0.0, x2 - x1)
    box_h = max(0.0, y2 - y1)

    norm_x1 = round(x1 / safe_w, 4)
    norm_y1 = round(y1 / safe_h, 4)
    norm_w = round(box_w / safe_w, 4)
    norm_h = round(box_h / safe_h, 4)

    # Percentage coordinates for direct CSS rendering in frontend overlays
    pct_x = round(norm_x1 * 100.0, 2)
    pct_y = round(norm_y1 * 100.0, 2)
    pct_w = round(norm_w * 100.0, 2)
    pct_h = round(norm_h * 100.0, 2)

    bbox = AnalysisBoundingBox(
        x1=round(x1, 2),
        y1=round(y1, 2),
        x2=round(x2, 2),
        y2=round(y2, 2),
        width=round(box_w, 2),
        height=round(box_h, 2),
        norm_x1=norm_x1,
        norm_y1=norm_y1,
        norm_w=norm_w,
        norm_h=norm_h,
        x=pct_x,
        y=pct_y,
        w=pct_w,
        h=pct_h,
    )

    has_geo = bool(geolocation and geolocation.latitude is not None and geolocation.longitude is not None)
    lat = geolocation.latitude if has_geo else None
    lon = geolocation.longitude if has_geo else None

    category = get_category_name(actual_result.raw_class_name)
    conf_bounded = max(0.0, min(1.0, float(actual_result.confidence)))

    coord_ref = "WGS 84 (Geographic 2D - EPSG:4326)" if has_geo else "UNAVAILABLE"
    meta_src = "Survey Towfish GPS Anchor (Image-Space Detection)" if has_geo else "Image-only sonar input"
    geo_note = (
        "Detection localized in sonar image-space with survey GPS anchor (towfish layback and acoustic slant-range ray tracing required for absolute seafloor coordinates)."
        if has_geo
        else "Image-only sonar input. No survey navigation metadata provided."
    )

    priority, priority_reason = determine_detection_priority(actual_result.raw_class_name)
    ev_status = "AVAILABLE" if evidence_available else "NOT AVAILABLE"
    intel = DetectionIntelligence(
        priority=priority,
        priority_reason=priority_reason,
        review_status="PENDING REVIEW",
        evidence_status=ev_status,
    )

    alt_hypotheses: List[AlternativeHypothesis] = []
    if hasattr(actual_result, "competing_hypotheses") and actual_result.competing_hypotheses:
        for alt_item in actual_result.competing_hypotheses:
            if isinstance(alt_item, AlternativeHypothesis):
                alt_hypotheses.append(alt_item)
            elif isinstance(alt_item, dict):
                alt_hypotheses.append(AlternativeHypothesis(**alt_item))

    return AnalysisDetection(
        id=det_id,
        code=code,
        model=actual_result.model_name,
        class_id=actual_result.class_id,
        raw_class=actual_result.raw_class_name,
        display_class=display_class,
        category=category,
        competing_hypotheses=alt_hypotheses,
        className=display_class.upper(),
        type=display_class,
        status="PENDING REVIEW",
        priority=priority,
        priority_reason=priority_reason,
        review_status="PENDING REVIEW",
        evidence_status=ev_status,
        intelligence=intel,
        confidence=round(conf_bounded, 4),
        confidence_percent=round(conf_bounded * 100.0, 1),
        bbox=bbox,
        survey_latitude=lat,
        survey_longitude=lon,
        has_target_geolocation=False,
        target_geolocation_note=geo_note,
        geoLat=lat,
        geoLon=lon,
        latitude=lat,
        longitude=lon,
        coordinateReference=coord_ref,
        metadataSource=meta_src,
        imagePosition={
            "x": pct_x,
            "y": pct_y,
            "display": f"X: {round(pct_x)}%, Y: {round(pct_y)}%",
        },
    )


def get_highest_priority_detection(
    detections: List[AnalysisDetection],
) -> Optional[HighestPriorityDetectionSummary]:
    """Identify the single highest priority detection, breaking ties by confidence."""
    if not detections:
        return None
    sorted_dets = sorted(
        detections,
        key=lambda d: (PRIORITY_RANKS.get(d.priority, 0), d.confidence),
        reverse=True,
    )
    top = sorted_dets[0]
    return HighestPriorityDetectionSummary(
        detection_id=top.id,
        display_class=top.display_class,
        priority=top.priority or "LOW",
        confidence=top.confidence,
    )


def compute_analysis_summary(
    detections: List[AnalysisDetection],
    models_executed: Optional[List[str]] = None,
    execution_time_ms: float = 0.0,
) -> AnalysisSummary:
    """Calculate statistical metrics, priority distributions, and category aggregations across detections."""
    if models_executed is None:
        models_executed = list({d.model for d in detections if d.model})
    total = len(detections)
    by_type: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    high_count = 0
    medium_count = 0
    low_count = 0
    confs = [d.confidence for d in detections]

    for d in detections:
        by_type[d.display_class] = by_type.get(d.display_class, 0) + 1
        cat = d.category or d.display_class
        categories[cat] = categories.get(cat, 0) + 1

        p = (d.priority or "LOW").upper()
        if p == "HIGH":
            high_count += 1
        elif p == "MEDIUM":
            medium_count += 1
        else:
            low_count += 1

    highest = round(max(confs), 4) if confs else 0.0
    average = round(sum(confs) / total, 4) if total > 0 else 0.0
    highest_pri = get_highest_priority_detection(detections)

    return AnalysisSummary(
        total_detections=total,
        high_priority=high_count,
        medium_priority=medium_count,
        low_priority=low_count,
        categories=categories,
        objects_by_type=by_type,
        highest_priority_detection=highest_pri,
        highest_confidence=highest,
        average_confidence=average,
        models_executed=models_executed,
        execution_time_ms=round(execution_time_ms, 2),
    )

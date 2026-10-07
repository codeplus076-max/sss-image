"""Sonar Survey Analysis Pipeline Service.

Coordinates image preprocessing, multi-model execution, detection aggregation,
class normalization, and statistical summary generation.
"""

import gc
import logging
import time
import uuid
from typing import Any, List, Optional

logger = logging.getLogger(__name__)
from app.core.model_registry import (
    MODEL_REGISTRY,
    ModelDefinition,
    ModelNotFoundError,
    get_model_definition,
    list_registered_models,
)
from app.schemas.analysis import (
    AnalysisDetection,
    AnalysisGeolocation,
    AnalysisImageMetadata,
    AnalysisResponse,
    AnalysisSurveyMetadata,
)
from app.services.detection_normalizer import (
    build_analysis_detection,
    compute_analysis_summary,
    deduplicate_cross_model_detections,
)
from app.services.inference import inference_service
from app.services.model_loader import unload_model
from app.services.preprocessing_service import PreprocessedImage, preprocess_image_bytes

# Default ordered sequence of all verified models when 'all' is requested
DEFAULT_ANALYSIS_MODELS = ["cylinder", "ghostvision", "mines", "shipwreck", "subpipes"]


class ModelUnavailableError(ValueError):
    """Raised when an unavailable model (such as Natural Seabed) is requested."""
    pass


def resolve_analysis_models(selected_models: Optional[List[str]]) -> List[ModelDefinition]:
    """Validate and resolve requested model identifiers into ModelDefinition objects."""
    if not selected_models:
        return [MODEL_REGISTRY[k] for k in DEFAULT_ANALYSIS_MODELS]

    # Handle string with comma separation if passed as single element
    flattened: List[str] = []
    for item in selected_models:
        if isinstance(item, str) and "," in item:
            flattened.extend(part.strip() for part in item.split(",") if part.strip())
        elif isinstance(item, str) and item.strip():
            flattened.append(item.strip())

    if not flattened or any(m.lower() in ("all", "*") for m in flattened):
        return [MODEL_REGISTRY[k] for k in DEFAULT_ANALYSIS_MODELS]

    resolved_definitions: List[ModelDefinition] = []
    seen_keys = set()

    for model_name in flattened:
        clean = model_name.lower().strip()
        try:
            m_def = get_model_definition(clean)
            if m_def.key not in seen_keys:
                resolved_definitions.append(m_def)
                seen_keys.add(m_def.key)
        except ModelNotFoundError as e:
            raise ModelNotFoundError(str(e)) from e

    return resolved_definitions


class AnalysisService:
    """Orchestrates end-to-end Side-Scan Sonar survey analysis."""

    @staticmethod
    def analyze_sonar_image(
        file_bytes: bytes,
        filename: str = "sonar_input.png",
        content_type: Optional[str] = None,
        selected_models: Optional[List[str]] = None,
        geolocation: Optional[AnalysisGeolocation] = None,
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
        enable_seabed_gate: bool = False,
        seabed_clean_threshold: float = 0.92,
        enable_roi_reverify: bool = True,
        roi_clean_threshold: float = 0.70,
        progress_callback: Optional[Any] = None,
    ) -> AnalysisResponse:
        """Run complete analysis pipeline on an uploaded sonar image."""
        start_time = time.perf_counter()

        if progress_callback:
            progress_callback(0.12, "Conditioning sonar image and validating acoustic signal...")

        # 1. Image Preprocessing & Validation
        preprocessed: PreprocessedImage = preprocess_image_bytes(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )

        # 2. Resolve Target Models
        target_models: List[ModelDefinition] = resolve_analysis_models(selected_models)
        target_keys = [m.key for m in target_models]

        # 3. Two-Stage Pipeline: Stage 1 Seabed Triage Gate
        captured_triage = None
        bypass_downstream = False
        triage_model_key = "natural_seabed"

        only_seabed_requested = (len(target_models) == 1 and target_models[0].key == triage_model_key)

        if enable_seabed_gate or only_seabed_requested:
            if progress_callback:
                progress_callback(0.18, "Executing Stage 1: Natural Seabed classification & anomaly screening...")
            try:
                triage_res = inference_service.classify_seabed(
                    image=preprocessed.np_array,
                    clean_threshold=seabed_clean_threshold,
                )
                captured_triage = triage_res.model_dump()
                if only_seabed_requested:
                    bypass_downstream = True
                    logger.info("[Stage 1 Triage] Only natural_seabed model requested; skipping specialized detectors.")
                else:
                    logger.info(
                        f"[Stage 1 Triage] Triage complete: decision={triage_res.decision}, "
                        f"P_clean={triage_res.clean_probability:.4f}, P_anomaly={triage_res.anomaly_probability:.4f}. "
                        f"Proceeding to Stage 2 multi-model detectors for full anomaly inspection."
                    )
            except Exception as e:
                logger.warning(f"Stage 1 seabed triage failed, falling forward to Stage 2: {e}")

        # 4. Multi-Model Inference Execution (Stage 2)
        raw_detections = []
        models_failed = 0
        executed_keys = []

        if captured_triage is not None:
            executed_keys.append(triage_model_key)

        if bypass_downstream or only_seabed_requested:
            # Conclusively clean seabed or only seabed model requested -> skip specialized detectors
            if progress_callback:
                progress_callback(0.85, "Clean seabed confirmed. Downstream detector execution bypassed.")
        else:
            # Filter out natural_seabed from Stage 2 detector models since it was already run
            detector_models = [m for m in target_models if m.key != triage_model_key]
            total_models = max(1, len(detector_models))
            executed_keys.extend([m.key for m in detector_models])

            # Fast path: execute all detector models in a single remote ZeroGPU cloud pass (~2-3s instead of 60s)
            remote_batch = inference_service.try_predict_all_remote(
                target_models=detector_models,
                image=preprocessed.np_array,
                confidence=confidence if confidence is not None else 0.25,
            )
            if remote_batch is not None:
                raw_detections, remote_triage = remote_batch
                if remote_triage and not captured_triage:
                    captured_triage = remote_triage
                if progress_callback:
                    progress_callback(0.85, f"Remote ZeroGPU inference complete ({len(raw_detections)} contacts)")
            else:
                # Fallback path: sequential local execution
                for idx, model_def in enumerate(detector_models):
                    if progress_callback:
                        p_fraction = 0.20 + (0.65 * (idx / total_models))
                        progress_callback(p_fraction, f"Running {model_def.name} ({idx + 1}/{total_models})...")

                    try:
                        inf_resp = inference_service.predict(
                            name_or_key=model_def.key,
                            image=preprocessed.np_array,
                            confidence=confidence,
                            iou=iou,
                        )
                        triage_val = getattr(inf_resp, "triage", None)
                        if isinstance(triage_val, dict) and not captured_triage:
                            captured_triage = triage_val
                        raw_detections.extend(inf_resp.detections)
                    except Exception as e:
                        models_failed += 1
                        logger.warning(f"Inference error on model '{model_def.key}': {e}", exc_info=True)
                    finally:
                        if len(detector_models) > 1:
                            unload_model(model_def.key)
                    gc.collect()

        # ROI-level re-verification + physics guards: prune false alarms (voids, streaks, clean seabed)
        # to eliminate false positives before cross-model spatial deduplication.
        if enable_roi_reverify and raw_detections:
            if progress_callback:
                progress_callback(0.88, "Running localized ROI re-verification to suppress false positives...")
            verified_candidates = _roi_reverify_detections(
                detections=raw_detections,
                full_image=preprocessed.np_array,
                clean_threshold=roi_clean_threshold,
            )
        else:
            verified_candidates = raw_detections

        # Cross-model deduplication for overlapping models on remaining genuine contacts
        active_detections = deduplicate_cross_model_detections(verified_candidates, iou_threshold=0.25)

        # If no verified specialized targets remain, check seabed anomaly screening:
        # If an uncatalogued anomaly or wreck structure is confirmed (p_anomaly > 0.60),
        # extract candidate acoustic highlight/shadow regions and verify them.
        if not active_detections and len(target_models) > 0:
            p_anomaly = 0.0
            try:
                triage_res = inference_service.classify_seabed(image=preprocessed.np_array)
                captured_triage = triage_res.model_dump()
                p_anomaly = triage_res.anomaly_probability
            except Exception as e:
                logger.debug(f"Seabed anomaly screening skipped: {e}")

            # Fallback contrast heuristic: if all models failed, or if an uncatalogued anomaly is confirmed
            should_run_fallback = (models_failed == len(target_models) and models_failed > 0) or (p_anomaly > 0.60 and not active_detections)
            if should_run_fallback:
                anom_boxes = extract_acoustic_anomalies(
                    preprocessed.np_array,
                    confidence=confidence,
                )
                if enable_roi_reverify and anom_boxes:
                    active_detections = _roi_reverify_detections(
                        detections=anom_boxes,
                        full_image=preprocessed.np_array,
                        clean_threshold=roi_clean_threshold,
                    )
                else:
                    active_detections = anom_boxes

        if progress_callback:
            progress_callback(0.92, "Synthesizing detection intelligence and spatial bounding boxes...")

        # 4. Assemble Geolocation and Survey Metadata (Strict Geolocation Integrity)
        geo = geolocation or AnalysisGeolocation()
        has_geo = bool(geo.latitude is not None and geo.longitude is not None)
        geo.geolocation_available = has_geo
        if geo.depth is None and geo.depth_m is not None:
            geo.depth = geo.depth_m
        elif geo.depth_m is None and geo.depth is not None:
            geo.depth_m = geo.depth

        survey_meta = AnalysisSurveyMetadata(
            latitude=geo.latitude,
            longitude=geo.longitude,
            depth=geo.depth_m if geo.depth_m is not None else geo.depth,
            heading=geo.heading,
            timestamp=geo.timestamp,
            geolocation_available=has_geo,
        )

        analysis_id = f"SONAR-{uuid.uuid4().hex[:12].upper()}"
        evidence_url = f"/api/v1/analysis/{analysis_id}/evidence"

        # 5. Detection Normalization & Bounding Box Calculation
        normalized_detections: List[AnalysisDetection] = []
        for idx, raw_det in enumerate(active_detections):
            det = build_analysis_detection(
                result=raw_det,
                index=idx,
                image_width=preprocessed.width,
                image_height=preprocessed.height,
                geolocation=geo,
            )
            det.evidenceImage = evidence_url
            normalized_detections.append(det)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # 6. Statistical Summary Calculation
        summary = compute_analysis_summary(
            detections=normalized_detections,
            models_executed=executed_keys,
            execution_time_ms=elapsed_ms,
        )

        # 7. Assemble Final Structured Response
        image_meta = AnalysisImageMetadata(
            filename=preprocessed.filename,
            width=preprocessed.width,
            height=preprocessed.height,
            channels=preprocessed.channels,
            format=preprocessed.format,
            size_bytes=preprocessed.size_bytes,
        )

        return AnalysisResponse(
            analysis_id=analysis_id,
            status="completed",
            image=image_meta,
            geolocation=geo,
            metadata=survey_meta,
            detections=normalized_detections,
            summary=summary,
            triage=captured_triage if isinstance(captured_triage, dict) else None,
            evidence_url=evidence_url,
        )


analysis_service = AnalysisService()


def _roi_reverify_detections(
    detections: List[Any],
    full_image: "np.ndarray",
    clean_threshold: float = 0.70,
) -> List[Any]:
    """Re-verify each detection by running the natural_seabed classifier on its cropped ROI.

    Strategy:
    - Crop the exact bounding box region from the full sonar swath.
    - Classify the crop with `classify_seabed_roi()` using a lower threshold than the
      whole-image gate (default 0.70 vs 0.92) to be aggressive about suppressing
      false positives without masking real anomalies.
    - If the crop is confirmed as clean seabed AND the detection confidence is below
      a high-confidence exemption threshold (0.75), suppress the detection.
    - Detections with confidence >= 0.75 are kept unconditionally — the object detector
      is very sure, and the seabed classifier is less reliable at such high object conf.

    Args:
        detections: List of DetectionResult objects from multi-model inference.
        full_image: Full sonar swath as numpy array (HWC, RGB).
        clean_threshold: ROI p_clean threshold above which detection is suppressed.

    Returns:
        Filtered list with false-positive detections removed.
    """
    import numpy as np

    # High-confidence exemption: don't suppress if the detector is very confident
    HIGH_CONF_EXEMPT = 0.75

    kept = []
    h, w = full_image.shape[:2]

    for det in detections:
        try:
            bbox = det.bounding_box
            conf = det.confidence

            # Extract pixel coords, clamped to image bounds
            x1 = max(0, int(bbox.x1))
            y1 = max(0, int(bbox.y1))
            x2 = min(w, int(bbox.x2))
            y2 = min(h, int(bbox.y2))
            bw = x2 - x1
            bh = y2 - y1

            # Safety guard: ensure crop has meaningful area
            if bw < 8 or bh < 8:
                kept.append(det)
                continue

            # Physical Sonar Guard 1: Nadir / scanning stripe artifact (extreme horizontal stripe across swath or thin scanner sliver)
            is_nadir_stripe = bw > 0.35 * w and (bw / max(1, bh)) > 4.0
            is_thin_wreck_sliver = (
                "shipwreck" in det.raw_class_name.lower()
                and min(bw, bh) < 45
                and (max(bw, bh) / max(1, min(bw, bh))) > 3.5
            )
            if is_nadir_stripe or is_thin_wreck_sliver:
                logger.info(
                    f"[Physics Guard] Suppressed scanning stripe / sliver artifact ({bw}x{bh}) for '{det.semantic_class_name}'"
                )
                continue

            roi_crop = full_image[y1:y2, x1:x2]

            # Physical Sonar Guard 2: Acoustic dead-zone check (pitch-black water column void without acoustic reflection)
            if roi_crop.size > 0:
                crop_mean = float(roi_crop.mean())
                if crop_mean < 22.0 and float(np.percentile(roi_crop, 95)) < 50.0:
                    logger.info(
                        f"[Physics Guard] Suppressed acoustic void / dead zone (mean={crop_mean:.1f}) for '{det.semantic_class_name}'"
                    )
                    continue

                # Physical Sonar Guard 3: Margin / border watermark false alarms
                if crop_mean > 230.0:
                    logger.info(
                        f"[Physics Guard] Suppressed margin / border artifact (mean={crop_mean:.1f}) for '{det.semantic_class_name}'"
                    )
                    continue

            # High-confidence exemption or macro shipwreck exemption:
            # natural_seabed.pt is trained strictly on natural seafloor vs small ordnance debris,
            # not large shipwrecks, and falsely labels steel/wooden hull textures as clean seabed.
            # Shipwrecks that have passed the physics guards above are preserved.
            is_shipwreck = "shipwreck" in det.raw_class_name.lower()
            if conf >= HIGH_CONF_EXEMPT or is_shipwreck:
                kept.append(det)
                logger.debug(
                    f"[ROI Re-verify] KEPT '{det.semantic_class_name}' (conf={conf:.3f}, is_shipwreck={is_shipwreck})"
                )
                continue

            roi_result = inference_service.classify_seabed_roi(
                roi=roi_crop,
                clean_threshold=clean_threshold,
            )

            if roi_result.is_clean:
                logger.info(
                    f"[ROI Re-verify] SUPPRESSED detection '{det.semantic_class_name}' "
                    f"conf={conf:.3f} → ROI p_clean={roi_result.clean_probability:.3f} "
                    f"(threshold={clean_threshold}) — false positive eliminated"
                )
                # Don't append → detection suppressed
            else:
                kept.append(det)
                logger.debug(
                    f"[ROI Re-verify] KEPT '{det.semantic_class_name}' conf={conf:.3f} "
                    f"ROI p_clean={roi_result.clean_probability:.3f} ({roi_result.decision})"
                )
        except Exception as e:
            # On any ROI error, keep the detection to avoid silencing real anomalies
            logger.warning(f"[ROI Re-verify] Error classifying ROI, keeping detection: {e}")
            kept.append(det)

    suppressed = len(detections) - len(kept)
    if suppressed > 0:
        logger.info(f"[ROI Re-verify] Suppressed {suppressed}/{len(detections)} false-positive detections via ROI re-verification.")
    else:
        logger.debug(f"[ROI Re-verify] All {len(detections)} detections passed ROI re-verification.")

    return kept


def extract_acoustic_anomalies(
    img_rgb,
    confidence: Optional[float] = None,
) -> List[Any]:
    """Extract acoustic highlight and shadow targets directly using computer-vision contrast heuristics.

    Acts as a resilient fallback on CPU containers only if PyTorch model execution fails.
    Accurately classifies contacts as acoustic contrast anomalies without spoofing model predictions.
    """
    import cv2
    import numpy as np
    from app.schemas.inference import BoundingBox, DetectionResult

    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    p85 = float(np.percentile(blurred, 85))
    _, thresh = cv2.threshold(blurred, max(60, int(p85)), 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections = []
    min_area = (h * w) * 0.001
    max_area = (h * w) * 0.25

    valid_contours = []
    for c in contours:
        area = cv2.contourArea(c)
        if min_area <= area <= max_area:
            valid_contours.append((area, c))

    valid_contours.sort(key=lambda x: x[0], reverse=True)
    selected_contours = valid_contours[:1]

    if not selected_contours:
        return []

    for area, c in selected_contours:
        x, y, bw, bh = cv2.boundingRect(c)
        peak_val = float(np.max(gray[y:y+bh, x:x+bw])) if bw > 0 and bh > 0 else 180.0
        conf = round(min(0.85, max(0.40, (peak_val / 255.0) * 0.7 + 0.1)), 2)
        if confidence is not None and conf < confidence:
            continue

        norm_x1 = max(0.0, min(1.0, float(x) / max(1, w)))
        norm_y1 = max(0.0, min(1.0, float(y) / max(1, h)))
        norm_w = max(0.0, min(1.0, float(bw) / max(1, w)))
        norm_h = max(0.0, min(1.0, float(bh) / max(1, h)))

        bbox = BoundingBox(
            x1=round(float(x), 2),
            y1=round(float(y), 2),
            x2=round(float(x + bw), 2),
            y2=round(float(y + bh), 2),
            width=round(float(bw), 2),
            height=round(float(bh), 2),
            norm_x1=round(norm_x1, 4),
            norm_y1=round(norm_y1, 4),
            norm_w=round(norm_w, 4),
            norm_h=round(norm_h, 4),
        )

        det = DetectionResult(
            model_name="Acoustic Contrast Filter",
            class_id=0,
            raw_class_name="Acoustic Anomaly",
            semantic_class_name="Acoustic Contrast Anomaly (Highlight/Shadow)",
            confidence=conf,
            bounding_box=bbox,
            image_width=w,
            image_height=h,
        )
        detections.append(det)

    return detections


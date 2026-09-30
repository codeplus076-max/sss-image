"""Sonar Survey Analysis Pipeline Service.

Coordinates image preprocessing, multi-model execution, detection aggregation,
class normalization, and statistical summary generation.
"""

import gc
import time
import uuid
from typing import List, Optional
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
        if clean in ("natural_seabed", "naturalseabed", "seabed"):
            raise ModelUnavailableError(
                "The Natural Seabed model is currently unavailable in the repository."
            )

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
    ) -> AnalysisResponse:
        """Run complete analysis pipeline on an uploaded sonar image."""
        start_time = time.perf_counter()

        # 1. Image Preprocessing & Validation
        preprocessed: PreprocessedImage = preprocess_image_bytes(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )

        # 2. Resolve Target Models
        target_models: List[ModelDefinition] = resolve_analysis_models(selected_models)
        executed_keys = [m.key for m in target_models]

        # 3. Multi-Model Inference Execution
        raw_detections = []
        for model_def in target_models:
            # Each model runs using native resolution handled internally
            inf_resp = inference_service.predict(
                name_or_key=model_def.key,
                image=preprocessed.np_array,
                confidence=confidence,
                iou=iou,
            )
            raw_detections.extend(inf_resp.detections)
            gc.collect()

        # Conservative cross-model deduplication for overlapping models
        active_detections = deduplicate_cross_model_detections(raw_detections, iou_threshold=0.50)

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
            evidence_url=evidence_url,
        )


analysis_service = AnalysisService()

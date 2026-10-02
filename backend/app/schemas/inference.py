"""Pydantic schemas for normalized inference output, bounding boxes, and API prediction responses."""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized and pixel bounding box coordinates."""

    x1: float = Field(..., description="Top-left X coordinate in pixels")
    y1: float = Field(..., description="Top-left Y coordinate in pixels")
    x2: float = Field(..., description="Bottom-right X coordinate in pixels")
    y2: float = Field(..., description="Bottom-right Y coordinate in pixels")
    width: float = Field(..., description="Width of the bounding box in pixels")
    height: float = Field(..., description="Height of the bounding box in pixels")

    # Normalized coordinates [0.0 - 1.0] for responsive frontend display
    norm_x1: float = Field(..., description="Normalized top-left X [0.0 - 1.0]")
    norm_y1: float = Field(..., description="Normalized top-left Y [0.0 - 1.0]")
    norm_w: float = Field(..., description="Normalized width [0.0 - 1.0]")
    norm_h: float = Field(..., description="Normalized height [0.0 - 1.0]")


class DetectionResult(BaseModel):
    """Normalized single object detection result (internal service model)."""

    model_name: str = Field(..., description="Identifier of the model that generated the detection")
    class_id: int = Field(..., description="Raw integer class identifier")
    raw_class_name: str = Field(..., description="Original raw class name from training metadata")
    semantic_class_name: str = Field(..., description="Human-interpretable display label")
    confidence: float = Field(..., description="Detection confidence score [0.0 - 1.0]")
    bounding_box: BoundingBox = Field(..., description="Bounding box geometry")
    image_width: int = Field(..., description="Width of the analyzed image in pixels")
    image_height: int = Field(..., description="Height of the analyzed image in pixels")


class InferenceResponse(BaseModel):
    """Normalized response payload for an internal inference run."""

    model_name: str = Field(..., description="Name of the model executed")
    model_architecture: str = Field(..., description="YOLO architecture family")
    detections_count: int = Field(..., description="Total number of detections meeting threshold")
    detections: List[DetectionResult] = Field(default_factory=list, description="List of detected anomalies")
    image_width: int = Field(..., description="Input image width")
    image_height: int = Field(..., description="Input image height")
    inference_time_ms: float = Field(..., description="Inference latency in milliseconds")
    triage: Optional[Dict[str, Any]] = Field(default=None, description="Triage classification result")


class PredictModelInfo(BaseModel):
    """Metadata block for the model utilized during prediction."""

    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Human-readable model name")


class PredictImageInfo(BaseModel):
    """Metadata block for the image analyzed."""

    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")


class PredictDetectionItem(BaseModel):
    """Normalized detection item matching the public API specification."""

    class_id: int = Field(..., description="Integer class identifier")
    raw_class_name: str = Field(..., description="Original raw class name from training metadata")
    display_name: str = Field(..., description="Operator and UI-friendly semantic display name")
    confidence: float = Field(..., description="Detection confidence score [0.0 - 1.0]")
    bounding_box: BoundingBox = Field(..., description="Bounding box coordinates in pixels and normalized values")


class PredictResponse(BaseModel):
    """Public API response schema for POST /api/v1/inference/predict."""

    success: bool = Field(default=True, description="Indicates whether inference completed successfully")
    model: PredictModelInfo = Field(..., description="Metadata of the model executed")
    image: PredictImageInfo = Field(..., description="Dimensions of the analyzed image")
    detections: List[PredictDetectionItem] = Field(default_factory=list, description="List of detected objects")
    count: int = Field(..., description="Total count of detected objects")


class ModelHealthInfo(BaseModel):
    """Verification and health status for a registered model."""

    model_key: str
    name: str
    architecture: str
    input_size: Tuple[int, int]
    task: str
    exists_on_disk: bool
    is_loadable: bool
    classes_count: int
    raw_classes: Dict[int, str]
    semantic_labels: Dict[int, str]
    error_message: Optional[str] = None

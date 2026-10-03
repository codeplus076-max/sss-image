"""Model listing and metadata schemas."""

from typing import List, Tuple
from pydantic import BaseModel, Field


class ClassMappingItem(BaseModel):
    """Class ID to raw and semantic display names."""

    class_id: int = Field(..., description="Integer class ID from model training")
    raw_class_name: str = Field(..., description="Original raw class name from training metadata")
    display_name: str = Field(..., description="Operator and frontend-friendly semantic display label")


class ModelDetail(BaseModel):
    """Detailed metadata for a registered detection model."""

    id: str = Field(..., description="Canonical model identifier for API calls")
    name: str = Field(..., description="Human-readable model name")
    display_name: str = Field(..., description="Frontend display title")
    architecture: str = Field(..., description="YOLO architecture family")
    input_resolution: Tuple[int, int] = Field(..., description="Native input image dimensions (width, height)")
    task: str = Field(..., description="Model computer vision task (e.g. detect)")
    status: str = Field(..., description="Model availability ('available' or 'unavailable')")
    class_mappings: List[ClassMappingItem] = Field(default_factory=list, description="Class mappings for this model")
    notes: str = Field(default="", description="Operator guidance or model characteristics")


class ModelListResponse(BaseModel):
    """Response containing registered models."""

    models: List[ModelDetail] = Field(default_factory=list, description="List of registered detection models")
    total: int = Field(..., description="Total number of registered models")
    unavailable_models: List[str] = Field(
        default_factory=list,
        description="Models currently pending training or unavailable",
    )

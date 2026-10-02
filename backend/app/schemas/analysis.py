"""Schemas for Side-Scan Sonar Analysis Pipeline."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalysisBoundingBox(BaseModel):
    """Bounding box coordinates in pixels, normalized units, and CSS percentage values."""

    # Absolute Pixel Coordinates
    x1: float = Field(..., description="Top-left X pixel coordinate")
    y1: float = Field(..., description="Top-left Y pixel coordinate")
    x2: float = Field(..., description="Bottom-right X pixel coordinate")
    y2: float = Field(..., description="Bottom-right Y pixel coordinate")
    width: Optional[float] = Field(None, description="Width in pixels")
    height: Optional[float] = Field(None, description="Height in pixels")

    # Normalized Ratio Coordinates [0.0 - 1.0]
    norm_x1: Optional[float] = Field(None, description="Normalized X1 [0.0 - 1.0]")
    norm_y1: Optional[float] = Field(None, description="Normalized Y1 [0.0 - 1.0]")
    norm_w: Optional[float] = Field(None, description="Normalized Width [0.0 - 1.0]")
    norm_h: Optional[float] = Field(None, description="Normalized Height [0.0 - 1.0]")

    # Frontend CSS Percentage Overlay Coordinates [0.0 - 100.0]
    x: Optional[float] = Field(None, description="Left offset percentage [0 - 100%]")
    y: Optional[float] = Field(None, description="Top offset percentage [0 - 100%]")
    w: Optional[float] = Field(None, description="Width percentage [0 - 100%]")
    h: Optional[float] = Field(None, description="Height percentage [0 - 100%]")


class DetectionIntelligence(BaseModel):
    """Operator decision-support intelligence metadata for a single detection."""
    priority: str = Field(..., description="Operational review priority: 'HIGH', 'MEDIUM', or 'LOW'")
    priority_reason: str = Field(..., description="Transparent, rule-based rationale for priority assignment")
    review_status: str = Field("PENDING REVIEW", description="Operator review status: 'PENDING REVIEW', 'REVIEWED', or 'REQUIRES ATTENTION'")
    evidence_status: str = Field("AVAILABLE", description="Evidence asset availability: 'AVAILABLE' or 'NOT AVAILABLE'")


class HighestPriorityDetectionSummary(BaseModel):
    """Summary of the single highest-priority anomaly detection."""
    detection_id: str = Field(..., description="Unique detection identifier")
    display_class: str = Field(..., description="Normalized display class")
    priority: str = Field(..., description="Review priority level: 'HIGH', 'MEDIUM', or 'LOW'")
    confidence: float = Field(..., description="Confidence score [0.0 - 1.0]")


class AnalysisDetection(BaseModel):
    """Normalized detection item within a sonar survey analysis."""

    id: str = Field(..., description="Unique detection identifier (e.g. DET-01)")
    model: str = Field(..., description="Identifier of the model that generated the detection")
    class_id: int = Field(..., description="Raw integer class ID")
    raw_class: str = Field(..., description="Original raw model class label")
    display_class: str = Field(..., description="Normalized frontend semantic class label")
    category: Optional[str] = Field(None, description="Normalized high-level anomaly category")
    confidence: float = Field(..., description="Confidence score [0.0 - 1.0]")
    bbox: AnalysisBoundingBox = Field(..., description="Bounding box geometry")

    # Intelligence & Review Layer
    priority: Optional[str] = Field("LOW", description="Operational review priority: 'HIGH', 'MEDIUM', or 'LOW'")
    priority_reason: Optional[str] = Field(None, description="Transparent, rule-based rationale for priority assignment")
    review_status: Optional[str] = Field("PENDING REVIEW", description="Operator review status")
    evidence_status: Optional[str] = Field("AVAILABLE", description="Evidence availability indicator")
    intelligence: Optional[DetectionIntelligence] = Field(None, description="Structured intelligence decision-support object")

    # Frontend-friendly UI binding fields
    code: Optional[str] = Field(None, description="Sequential detection number code (e.g. '01')")
    className: Optional[str] = Field(None, description="Uppercase class identifier (e.g. 'SHIPWRECK')")
    type: Optional[str] = Field(None, description="Descriptive semantic anomaly type")
    status: Optional[str] = Field("PENDING REVIEW", description="Operator review status")
    confidence_percent: Optional[float] = Field(None, description="Confidence score percentage [0 - 100]")
    # Explicit survey-level anchor vs detection image-space position
    survey_latitude: Optional[float] = Field(None, description="Survey towfish geographic latitude anchor")
    survey_longitude: Optional[float] = Field(None, description="Survey towfish geographic longitude anchor")
    has_target_geolocation: bool = Field(False, description="False: detection is unprojected in image-space")
    target_geolocation_note: Optional[str] = Field(
        None,
        description="Explains distinction between survey vessel/towfish position and image-space target localization"
    )

    # Frontend-friendly UI binding fields (backward-compatible aliases)
    geoLat: Optional[float] = Field(None, description="Survey latitude anchor alias")
    geoLon: Optional[float] = Field(None, description="Survey longitude anchor alias")
    latitude: Optional[float] = Field(None, description="Survey latitude coordinate alias")
    longitude: Optional[float] = Field(None, description="Survey longitude coordinate alias")
    coordinateReference: Optional[str] = Field(None, description="Spatial reference system (e.g. 'WGS 84 (Geographic 2D - EPSG:4326)')")
    metadataSource: Optional[str] = Field(None, description="Telemetry source description")
    imagePosition: Optional[Dict[str, Any]] = Field(None, description="UI position display formatting")
    evidenceImage: Optional[str] = Field(None, description="Relative access URL to evidence image")


class AnalysisImageMetadata(BaseModel):
    """Image metadata for the analyzed sonar file."""

    filename: str = Field(..., description="Original name of the uploaded image")
    width: int = Field(..., description="Width in pixels")
    height: int = Field(..., description="Height in pixels")
    channels: Optional[int] = Field(3, description="Color channel count")
    format: Optional[str] = Field(None, description="Detected image format (JPEG, PNG, TIFF, etc.)")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")


class AnalysisGeolocation(BaseModel):
    """Real navigation telemetry associated with the sonar survey. Never mocked."""

    latitude: Optional[float] = Field(None, description="WGS84 Latitude in decimal degrees")
    longitude: Optional[float] = Field(None, description="WGS84 Longitude in decimal degrees")
    depth_m: Optional[float] = Field(None, description="Sensor/seabed depth in meters")
    depth: Optional[float] = Field(None, description="Sensor/seabed depth in meters (alias for depth_m)")
    heading: Optional[float] = Field(None, description="Towfish heading in degrees [0 - 360]")
    timestamp: Optional[str] = Field(None, description="Survey ping timestamp (ISO 8601)")
    geolocation_available: bool = Field(False, description="True if real geographic coordinates are present")


class AnalysisSurveyMetadata(BaseModel):
    """Survey navigation and sensor metadata with geolocation integrity status."""

    latitude: Optional[float] = Field(None, description="Real WGS84 survey latitude [-90.0 to 90.0]. Never fabricated.")
    longitude: Optional[float] = Field(None, description="Real WGS84 survey longitude [-180.0 to 180.0]. Never fabricated.")
    depth: Optional[float] = Field(None, description="Sensor/seabed depth in meters.")
    heading: Optional[float] = Field(None, description="Towfish heading in degrees [0.0 - 360.0).")
    timestamp: Optional[str] = Field(None, description="Survey ping timestamp (ISO 8601).")
    geolocation_available: bool = Field(False, description="True if real geographic coordinates (lat & lon) are present.")


class AnalysisSummary(BaseModel):
    """Statistical summary of detected anomalies."""

    total_detections: int = Field(..., description="Total count of anomalies detected")
    high_priority: int = Field(0, description="Count of detections designated as HIGH priority")
    medium_priority: int = Field(0, description="Count of detections designated as MEDIUM priority")
    low_priority: int = Field(0, description="Count of detections designated as LOW priority")
    categories: Dict[str, int] = Field(
        default_factory=dict, description="Anomaly count aggregated by normalized high-level category"
    )
    objects_by_type: Dict[str, int] = Field(
        default_factory=dict, description="Anomaly count aggregated by normalized display class"
    )
    highest_priority_detection: Optional[HighestPriorityDetectionSummary] = Field(
        None, description="Detection with highest operational review priority (tie-broken by confidence)"
    )
    highest_confidence: float = Field(0.0, description="Maximum confidence score among detections")
    average_confidence: float = Field(0.0, description="Mean confidence score among detections")
    models_executed: List[str] = Field(
        default_factory=list, description="List of models that executed during this analysis"
    )
    execution_time_ms: float = Field(0.0, description="Total pipeline execution time in milliseconds")


class AnalysisResponse(BaseModel):
    """Complete response payload for POST /api/v1/analysis/analyze."""

    analysis_id: str = Field(..., description="Unique UUID for this analysis run")
    status: str = Field(default="completed", description="Analysis status ('completed' or 'failed')")
    image: AnalysisImageMetadata = Field(..., description="Image dimensions and metadata")
    geolocation: AnalysisGeolocation = Field(
        default_factory=AnalysisGeolocation,
        description="Navigation telemetry if provided (strictly null if absent)",
    )
    metadata: AnalysisSurveyMetadata = Field(
        default_factory=AnalysisSurveyMetadata,
        description="Survey metadata and geolocation status",
    )
    detections: List[AnalysisDetection] = Field(
        default_factory=list, description="List of all verified anomaly detections"
    )
    summary: AnalysisSummary = Field(..., description="Aggregated detection statistics")
    triage: Optional[Dict[str, Any]] = Field(
        None, description="Seabed classification triage results (clean seabed vs anomaly)"
    )
    evidence_url: Optional[str] = Field(None, description="Endpoint to access the uploaded evidence image")


class AnalysisEvidence(BaseModel):
    """Metadata for the stored sonar evidence image."""

    original_filename: str = Field(..., description="Original uploaded filename")
    content_type: str = Field(..., description="MIME content type")
    size_bytes: int = Field(..., description="File size in bytes")
    storage_path: str = Field(..., description="Internal object storage path")
    access_url: Optional[str] = Field(None, description="Relative access URL to view the evidence image")
    created_at: Optional[datetime] = Field(None, description="UTC creation timestamp")


class AnalysisDetailResponse(AnalysisResponse):
    """Detailed response for GET /api/v1/analysis/{analysis_id} including evidence metadata."""

    created_at: Optional[datetime] = Field(None, description="Timestamp of survey analysis record creation")
    evidence: Optional[AnalysisEvidence] = Field(None, description="Evidence image storage metadata")


class PaginatedAnalysisResponse(BaseModel):
    """Paginated list of previous analyses for GET /api/v1/analysis."""

    total: int = Field(..., description="Total number of matching analyses")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total pages available")
    items: List[AnalysisDetailResponse] = Field(default_factory=list, description="List of analyses on this page")


class DeleteAnalysisResponse(BaseModel):
    """Response payload for DELETE /api/v1/analysis/{analysis_id}."""

    status: str = Field(default="deleted", description="Operation status")
    analysis_id: str = Field(..., description="Identifier of the deleted analysis")
    message: str = Field(..., description="Confirmation message")


class SonarValidationErrorResponse(BaseModel):
    """Response payload returned when uploaded image fails sonar-likeness validation."""

    error: str = Field(default="INVALID_SONAR_IMAGE", description="Error category code")
    message: str = Field(..., description="High-level user-facing error message")
    details: str = Field(..., description="Actionable guidance for the operator")


class JobSubmissionResponse(BaseModel):
    """Response returned upon successful asynchronous job creation."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(default="queued", description="Initial job status ('queued' or 'processing')")
    progress: float = Field(default=0.05, description="Initial progress")
    current_step: str = Field(..., description="Current status message")
    created_at: str = Field(..., description="ISO-8601 creation timestamp")
    poll_url: str = Field(..., description="URL to poll for job progress and results")


class JobStatusResponse(BaseModel):
    """Status and result response for GET /api/v1/analysis/jobs/{job_id}."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status: 'queued', 'processing', 'completed', or 'failed'")
    progress: float = Field(..., description="Completion progress [0.0 - 1.0]")
    current_step: Optional[str] = Field(None, description="Current workflow step description")
    created_at: str = Field(..., description="ISO-8601 creation timestamp")
    updated_at: Optional[str] = Field(None, description="ISO-8601 last update timestamp")
    poll_url: str = Field(..., description="URL to poll for job status")
    error: Optional[str] = Field(None, description="Error details if status is 'failed'")
    result: Optional[AnalysisResponse] = Field(None, description="Full analysis response if status is 'completed'")

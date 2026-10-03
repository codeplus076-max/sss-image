"""Analysis route handler for API v1."""

from datetime import datetime
import json
import logging
from typing import Any, List, Optional, Union
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_registry import ModelNotFoundError
from app.db.session import get_db
from app.schemas.analysis import (
    AnalysisDetailResponse,
    AnalysisGeolocation,
    AnalysisResponse,
    DeleteAnalysisResponse,
    JobStatusResponse,
    JobSubmissionResponse,
    PaginatedAnalysisResponse,
    SonarValidationErrorResponse,
)
from app.services.analysis_persistence_service import (
    PersistenceError,
    analysis_persistence_service,
)
from app.services.analysis_service import ModelUnavailableError, analysis_service
from app.services.job_service import job_service
from app.services.preprocessing_service import ImageValidationError, UnsupportedFormatError
from app.services.sonar_image_validator import NonSonarImageError, sonar_validator
from app.services.storage_service import StorageError

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_float(value: Any, field_name: str) -> Optional[float]:
    """Parse and validate an optional numeric float field from form data."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    str_val = str(value).strip()
    if not str_val:
        return None
    try:
        return float(str_val)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid numeric value.",
        )


def _validate_iso8601_timestamp(ts: Optional[str]) -> Optional[str]:
    """Validate that timestamp follows ISO-8601 representation."""
    if ts is None:
        return None
    str_ts = str(ts).strip()
    if not str_ts:
        return None

    if len(str_ts) < 10 or "-" not in str_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timestamp must be a valid ISO-8601 formatted date/time string.",
        )
    try:
        norm = str_ts.replace("Z", "+00:00") if str_ts.endswith("Z") else str_ts
        datetime.fromisoformat(norm)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timestamp must be a valid ISO-8601 formatted date/time string.",
        )
    return str_ts


def _parse_selected_models(raw_input: Optional[str]) -> Optional[List[str]]:
    """Parse selected_models from comma-separated string or JSON array string."""
    if not raw_input or not raw_input.strip():
        return None

    raw_clean = raw_input.strip()
    if raw_clean.startswith("[") and raw_clean.endswith("]"):
        try:
            parsed = json.loads(raw_clean)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    return [part.strip() for part in raw_clean.split(",") if part.strip()]


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Comprehensive Side-Scan Sonar Analysis Pipeline",
    description="Uploads a sonar survey image, validates quality, runs specified or all AI anomaly models, aggregates detections, normalizes semantic classes, persists analysis and evidence to database and storage, and returns results.",
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": SonarValidationErrorResponse,
            "description": "Uploaded image is not a valid Side-Scan Sonar image",
        }
    },
)
def analyze_sonar_survey(
    image: UploadFile = File(..., description="Uploaded sonar image file (JPEG, PNG, TIFF, BMP, WebP)"),
    selected_models: Optional[str] = Form(
        None,
        description="Optional comma-separated list or JSON array of models to run (e.g. 'ghostvision,pipeline'). If omitted, runs all available models.",
    ),
    latitude: Optional[Union[float, str]] = Form(
        None, description="Optional real WGS84 survey latitude [-90.0 to 90.0]. Never fabricated."
    ),
    longitude: Optional[Union[float, str]] = Form(
        None, description="Optional real WGS84 survey longitude [-180.0 to 180.0]. Never fabricated."
    ),
    depth: Optional[Union[float, str]] = Form(
        None, description="Optional sensor/seabed depth in meters (non-negative numeric value)."
    ),
    heading: Optional[Union[float, str]] = Form(
        None, description="Optional towfish heading in degrees [0.0 - 360.0)."
    ),
    timestamp: Optional[str] = Form(
        None, description="Optional survey ping ISO-8601 timestamp."
    ),
    confidence: Optional[Union[float, str]] = Form(
        None, description="Optional detection confidence cutoff [0.0 - 1.0]."
    ),
    iou: Optional[Union[float, str]] = Form(
        None, description="Optional NMS IoU threshold [0.0 - 1.0]."
    ),
    enable_seabed_gate: Optional[Union[bool, str]] = Form(
        True, description="Enable Stage 1 natural seabed classification gate."
    ),
    seabed_clean_threshold: Optional[Union[float, str]] = Form(
        0.92, description="Clean seabed probability threshold [0.50 - 0.99] to bypass Stage 2 detectors."
    ),
    db: Session = Depends(get_db),
) -> Union[AnalysisResponse, JSONResponse]:
    """Analyze a sonar image through the end-to-end multi-model pipeline and persist results."""

    # 1. Parameter Type & Range Validations (Early rejection before image processing or inference)
    conf_val = _parse_float(confidence, "Confidence threshold")
    if conf_val is not None and not (0.0 <= conf_val <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confidence threshold must be between 0.0 and 1.0.",
        )

    gate_val = True
    if enable_seabed_gate is not None:
        if isinstance(enable_seabed_gate, bool):
            gate_val = enable_seabed_gate
        elif isinstance(enable_seabed_gate, str):
            gate_val = enable_seabed_gate.strip().lower() not in ("false", "0", "no", "off")

    clean_thresh_val = _parse_float(seabed_clean_threshold, "Seabed clean threshold")
    if clean_thresh_val is None:
        clean_thresh_val = 0.92
    elif not (0.50 <= clean_thresh_val <= 0.99):
        clean_thresh_val = max(0.50, min(0.99, clean_thresh_val))

    iou_val = _parse_float(iou, "IoU threshold")
    if iou_val is not None and not (0.0 <= iou_val <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IoU threshold must be between 0.0 and 1.0.",
        )

    lat_val = _parse_float(latitude, "Latitude")
    if lat_val is not None and not (-90.0 <= lat_val <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Latitude must be between -90.0 and 90.0 degrees.",
        )

    lon_val = _parse_float(longitude, "Longitude")
    if lon_val is not None and not (-180.0 <= lon_val <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Longitude must be between -180.0 and 180.0 degrees.",
        )

    depth_val = _parse_float(depth, "Depth")
    if depth_val is not None and depth_val < 0.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Depth must be a non-negative numeric value (meters).",
        )

    heading_val = _parse_float(heading, "Heading")
    if heading_val is not None and not (0.0 <= heading_val < 360.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Heading must be between 0.0 and 360.0 degrees.",
        )

    ts_val = _validate_iso8601_timestamp(timestamp)

    # 2. Read Image Data
    try:
        file_bytes = image.file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded image stream.",
        )

    # 3. Sonar Image Gate & Validation (Executed BEFORE model inference)
    try:
        sonar_validator.validate_upload(
            file_bytes=file_bytes,
            filename=image.filename or "sonar_image.png",
            content_type=image.content_type,
        )
    except UnsupportedFormatError as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(e),
        )
    except ImageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except NonSonarImageError as e:
        logger.info(f"Non-sonar image rejected with HTTP 422: {e.message}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "INVALID_SONAR_IMAGE",
                "message": e.message,
                "details": e.details,
            },
        )

    # 4. Parse Models List
    model_list = _parse_selected_models(selected_models)

    # 5. Assemble Geolocation (preserving provided values, never fabricating)
    has_geo = bool(lat_val is not None and lon_val is not None)
    geolocation = AnalysisGeolocation(
        latitude=lat_val,
        longitude=lon_val,
        depth_m=depth_val,
        depth=depth_val,
        heading=heading_val,
        timestamp=ts_val,
        geolocation_available=has_geo,
    )

    # 6. Run Complete Analysis Pipeline
    try:
        response = analysis_service.analyze_sonar_image(
            file_bytes=file_bytes,
            filename=image.filename or "sonar_image.png",
            content_type=image.content_type,
            selected_models=model_list,
            geolocation=geolocation,
            confidence=conf_val,
            iou=iou_val,
            enable_seabed_gate=gate_val,
            seabed_clean_threshold=clean_thresh_val,
        )
    except UnsupportedFormatError as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(e),
        )
    except ImageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ModelUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected pipeline error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {e}",
        )

    # 6. Persistent Storage of Evidence and Analysis Session
    try:
        analysis_persistence_service.persist_analysis(
            analysis_response=response,
            file_bytes=file_bytes,
            content_type=image.content_type,
            db=db,
        )
    except PersistenceError as e:
        logger.error(f"Persistence error for {response.analysis_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persistence error: {e}",
        )

    return response


def _run_async_analysis_pipeline(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str],
    model_list: Optional[List[str]],
    geolocation: AnalysisGeolocation,
    confidence: Optional[float],
    iou: Optional[float],
    enable_seabed_gate: bool = True,
    seabed_clean_threshold: float = 0.92,
):
    """Background task worker for asynchronous analysis job."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job_service.update_progress(job_id, 0.10, "Validating sonar image acoustics...")

        # 1. Sonar-likeness validation
        sonar_validator.validate_upload(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )

        def _on_progress(progress_val: float, step_msg: str):
            job_service.update_progress(job_id, progress_val, step_msg)

        # 2. Multi-model analysis
        analysis_res = analysis_service.analyze_sonar_image(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            selected_models=model_list,
            geolocation=geolocation,
            confidence=confidence,
            iou=iou,
            enable_seabed_gate=enable_seabed_gate,
            seabed_clean_threshold=seabed_clean_threshold,
            progress_callback=_on_progress,
        )

        job_service.update_progress(job_id, 0.95, "Storing analysis session and evidence records...")

        # 3. Persistent Storage
        analysis_persistence_service.persist_analysis(
            analysis_response=analysis_res,
            file_bytes=file_bytes,
            content_type=content_type,
            db=db,
        )

        job_service.complete_job(job_id, analysis_res)
    except NonSonarImageError as e:
        job_service.fail_job(job_id, f"Invalid sonar image: {e}")
    except Exception as e:
        logger.error(f"Async job '{job_id}' error: {e}", exc_info=True)
        job_service.fail_job(job_id, str(e))
    finally:
        db.close()


@router.post(
    "/jobs",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Asynchronous Sonar Survey Analysis Job",
    description="Accepts an image and parameters, queues background multi-model analysis, and immediately returns a job ID to poll, eliminating gateway timeouts.",
)
async def submit_analysis_job(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="Uploaded sonar image file (JPEG, PNG, TIFF, BMP, WebP)"),
    selected_models: Optional[str] = Form(None),
    latitude: Optional[Union[float, str]] = Form(None),
    longitude: Optional[Union[float, str]] = Form(None),
    depth: Optional[Union[float, str]] = Form(None),
    heading: Optional[Union[float, str]] = Form(None),
    timestamp: Optional[str] = Form(None),
    confidence: Optional[Union[float, str]] = Form(None),
    iou: Optional[Union[float, str]] = Form(None),
    enable_seabed_gate: Optional[Union[bool, str]] = Form(
        True, description="Enable Stage 1 natural seabed classification gate."
    ),
    seabed_clean_threshold: Optional[Union[float, str]] = Form(
        0.92, description="Clean seabed probability threshold [0.50 - 0.99] to bypass Stage 2 detectors."
    ),
) -> JobSubmissionResponse:
    """Submit a survey image for non-blocking asynchronous analysis."""
    # 1. Parameter Type & Range Validations
    conf_val = _parse_float(confidence, "Confidence threshold")
    if conf_val is not None and not (0.0 <= conf_val <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confidence threshold must be between 0.0 and 1.0.",
        )

    gate_val = True
    if enable_seabed_gate is not None:
        if isinstance(enable_seabed_gate, bool):
            gate_val = enable_seabed_gate
        elif isinstance(enable_seabed_gate, str):
            gate_val = enable_seabed_gate.strip().lower() not in ("false", "0", "no", "off")

    clean_thresh_val = _parse_float(seabed_clean_threshold, "Seabed clean threshold")
    if clean_thresh_val is None:
        clean_thresh_val = 0.92
    elif not (0.50 <= clean_thresh_val <= 0.99):
        clean_thresh_val = max(0.50, min(0.99, clean_thresh_val))

    iou_val = _parse_float(iou, "IoU threshold")
    if iou_val is not None and not (0.0 <= iou_val <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IoU threshold must be between 0.0 and 1.0.",
        )

    lat_val = _parse_float(latitude, "Latitude")
    if lat_val is not None and not (-90.0 <= lat_val <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Latitude must be between -90.0 and 90.0 degrees.",
        )

    lon_val = _parse_float(longitude, "Longitude")
    if lon_val is not None and not (-180.0 <= lon_val <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Longitude must be between -180.0 and 180.0 degrees.",
        )

    depth_val = _parse_float(depth, "Depth")
    if depth_val is not None and depth_val < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Depth must be a non-negative numeric value.",
        )

    heading_val = _parse_float(heading, "Heading")
    if heading_val is not None and not (0.0 <= heading_val < 360.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Heading must be in the range [0.0, 360.0) degrees.",
        )

    valid_timestamp = _validate_iso8601_timestamp(timestamp)
    model_list = _parse_selected_models(selected_models)

    # 2. Read Uploaded Image Bytes
    try:
        file_bytes = await image.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded image bytes: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded image data.",
        )

    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    # 3. Create Asynchronous Job
    job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
    filename = image.filename or "sonar_image.png"
    job_entry = job_service.create_job(job_id=job_id, original_filename=filename)

    geolocation = AnalysisGeolocation(
        latitude=lat_val,
        longitude=lon_val,
        depth_m=depth_val,
        depth=depth_val,
        heading=heading_val,
        timestamp=valid_timestamp,
        geolocation_available=bool(lat_val is not None and lon_val is not None),
    )

    # 4. Enqueue Background Execution
    background_tasks.add_task(
        _run_async_analysis_pipeline,
        job_id=job_id,
        file_bytes=file_bytes,
        filename=filename,
        content_type=image.content_type,
        model_list=model_list,
        geolocation=geolocation,
        confidence=conf_val,
        iou=iou_val,
        enable_seabed_gate=gate_val,
        seabed_clean_threshold=clean_thresh_val,
    )

    return JobSubmissionResponse(
        job_id=job_id,
        status="queued",
        progress=0.05,
        current_step="Survey registered in execution queue",
        created_at=job_entry["created_at"],
        poll_url=job_entry["poll_url"],
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Asynchronous Analysis Job Status & Result",
    description="Returns current progress, status, and full analysis response once completed.",
)
async def get_analysis_job_status(job_id: str) -> JobStatusResponse:
    """Check progress or retrieve result of an asynchronous analysis job."""
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobStatusResponse(**job)


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Detailed Analysis by ID",
    description="Returns full persisted analysis session, including detections, summary, geolocation, and evidence metadata.",
)
async def get_analysis_by_id(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> AnalysisDetailResponse:
    """Retrieve complete persisted analysis details by analysis_id."""
    analysis = analysis_persistence_service.get_analysis_by_id(analysis_id, db)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID '{analysis_id}' not found.",
        )
    return analysis


@router.get(
    "",
    response_model=PaginatedAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="List Persisted Sonar Analyses",
    description="Returns a paginated list of previous analyses with optional filtering by status or detected object type.",
)
async def list_analyses(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. 'completed')"),
    detection_type: Optional[str] = Query(None, description="Filter by detected object type"),
    db: Session = Depends(get_db),
) -> PaginatedAnalysisResponse:
    """Retrieve paginated analyses history with optional filtering."""
    return analysis_persistence_service.list_analyses(
        page=page,
        page_size=page_size,
        status=status_filter,
        detection_type=detection_type,
        db=db,
    )


@router.delete(
    "/{analysis_id}",
    response_model=DeleteAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Analysis and Stored Evidence",
    description="Permanently deletes an analysis session, its detection results, and the associated stored evidence image.",
)
async def delete_analysis_by_id(
    analysis_id: str,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    db: Session = Depends(get_db),
) -> DeleteAnalysisResponse:
    """Delete an analysis and associated evidence from DB and storage."""
    if settings.ADMIN_API_KEY and x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Valid X-Admin-Key header is required to delete survey analyses.",
        )
    deleted = analysis_persistence_service.delete_analysis(analysis_id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID '{analysis_id}' not found.",
        )
    return DeleteAnalysisResponse(
        status="deleted",
        analysis_id=analysis_id,
        message=f"Analysis '{analysis_id}' and associated evidence removed successfully.",
    )


@router.get(
    "/{analysis_id}/evidence",
    summary="Retrieve Stored Sonar Evidence Image",
    description="Streams the original stored sonar survey image file without exposing internal credentials.",
)
async def get_analysis_evidence(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Retrieve and stream the original sonar evidence image."""
    try:
        data, content_type, filename = analysis_persistence_service.get_evidence_file(analysis_id, db)
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

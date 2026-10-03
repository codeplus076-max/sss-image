"""Analysis persistence service coordinating DB operations and evidence storage."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import AnalysisRecord
from app.repositories.analysis_repository import AnalysisRepository
from app.schemas.analysis import (
    AnalysisBoundingBox,
    AnalysisDetailResponse,
    AnalysisDetection,
    AnalysisEvidence,
    AnalysisGeolocation,
    AnalysisImageMetadata,
    AnalysisResponse,
    AnalysisSummary,
    AnalysisSurveyMetadata,
    PaginatedAnalysisResponse,
    DetectionIntelligence,
)
from app.services.detection_normalizer import (
    compute_analysis_summary,
    determine_detection_priority,
    get_category_name,
)
from app.services.storage_service import StorageError, StorageService, storage_service

logger = logging.getLogger(__name__)


class PersistenceError(Exception):
    """Raised when persistence or evidence storage fails."""
    pass


class AnalysisPersistenceService:
    """Coordinates evidence storage and database transactions."""

    def __init__(self, storage: Optional[StorageService] = None):
        self.storage = storage or storage_service

    def persist_analysis(
        self,
        analysis_response: AnalysisResponse,
        file_bytes: bytes,
        content_type: Optional[str],
        db: Session,
    ) -> AnalysisRecord:
        """Store evidence image and persist analysis, detections, and metadata atomically."""
        analysis_id = analysis_response.analysis_id
        filename = analysis_response.image.filename
        content_type = content_type or "image/png"

        # Step 1: Store original evidence image
        try:
            storage_path = self.storage.save_evidence(
                analysis_id=analysis_id,
                filename=filename,
                data=file_bytes,
                content_type=content_type,
            )
        except Exception as e:
            logger.error(f"Storage failure for analysis {analysis_id}: {e}")
            raise PersistenceError(f"Evidence image storage failed: {e}") from e

        # Step 2: Prepare database records
        analysis_data: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "status": analysis_response.status,
            "original_filename": filename,
            "image_width": analysis_response.image.width,
            "image_height": analysis_response.image.height,
            "image_channels": analysis_response.image.channels or 3,
            "image_format": analysis_response.image.format,
            "image_size_bytes": analysis_response.image.size_bytes or len(file_bytes),
            "latitude": analysis_response.geolocation.latitude if analysis_response.geolocation else None,
            "longitude": analysis_response.geolocation.longitude if analysis_response.geolocation else None,
            "depth_m": analysis_response.geolocation.depth_m if analysis_response.geolocation else None,
            "heading": analysis_response.geolocation.heading if analysis_response.geolocation else None,
            "timestamp": analysis_response.geolocation.timestamp if analysis_response.geolocation else None,
            "total_detections": analysis_response.summary.total_detections,
            "highest_confidence": analysis_response.summary.highest_confidence,
            "average_confidence": analysis_response.summary.average_confidence,
            "models_executed": analysis_response.summary.models_executed,
            "objects_by_type": analysis_response.summary.objects_by_type,
            "execution_time_ms": analysis_response.summary.execution_time_ms,
            "triage": analysis_response.triage,
        }

        evidence_data: Dict[str, Any] = {
            "original_filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
            "storage_path": storage_path,
            "storage_provider": settings.STORAGE_PROVIDER,
        }

        detections_data: List[Dict[str, Any]] = []
        for det in analysis_response.detections:
            w = det.bbox.width if det.bbox.width is not None else max(0.0, det.bbox.x2 - det.bbox.x1)
            h = det.bbox.height if det.bbox.height is not None else max(0.0, det.bbox.y2 - det.bbox.y1)
            detections_data.append(
                {
                    "detection_id": det.id,
                    "model": det.model,
                    "class_id": det.class_id,
                    "raw_class": det.raw_class,
                    "display_class": det.display_class,
                    "confidence": det.confidence,
                    "x1": det.bbox.x1,
                    "y1": det.bbox.y1,
                    "x2": det.bbox.x2,
                    "y2": det.bbox.y2,
                    "width": w,
                    "height": h,
                    "norm_x1": det.bbox.norm_x1 if det.bbox.norm_x1 is not None else 0.0,
                    "norm_y1": det.bbox.norm_y1 if det.bbox.norm_y1 is not None else 0.0,
                    "norm_w": det.bbox.norm_w if det.bbox.norm_w is not None else 0.0,
                    "norm_h": det.bbox.norm_h if det.bbox.norm_h is not None else 0.0,
                    "competing_hypotheses": [
                        h.model_dump() if hasattr(h, "model_dump") else h
                        for h in (getattr(det, "competing_hypotheses", None) or [])
                    ],
                }
            )

        # Step 3: Atomic database persistence with cleanup on failure
        repo = AnalysisRepository(db)
        try:
            record = repo.create_analysis(
                analysis_data=analysis_data,
                detections_data=detections_data,
                evidence_data=evidence_data,
            )
            return record
        except Exception as db_err:
            logger.error(
                f"Database insertion failed for analysis {analysis_id}. Cleaning up evidence {storage_path}..."
            )
            try:
                self.storage.delete_evidence(storage_path)
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup evidence file {storage_path}: {cleanup_err}")
            raise PersistenceError(f"Database persistence failed: {db_err}") from db_err

    def record_to_detail_response(self, record: AnalysisRecord) -> AnalysisDetailResponse:
        """Convert an AnalysisRecord ORM entity to an AnalysisDetailResponse schema."""
        evidence_schema = None
        if record.evidence:
            evidence_schema = AnalysisEvidence(
                original_filename=record.evidence.original_filename,
                content_type=record.evidence.content_type,
                size_bytes=record.evidence.size_bytes,
                storage_path=record.evidence.storage_path,
                access_url=f"/api/v1/analysis/{record.analysis_id}/evidence",
                created_at=record.evidence.created_at,
            )

        evidence_url = f"/api/v1/analysis/{record.analysis_id}/evidence"
        has_geo = bool(record.latitude is not None and record.longitude is not None)

        detections = []
        for idx, det in enumerate(record.detections):
            pct_x = round(det.norm_x1 * 100.0, 2)
            pct_y = round(det.norm_y1 * 100.0, 2)
            pct_w = round(det.norm_w * 100.0, 2)
            pct_h = round(det.norm_h * 100.0, 2)
            code = f"{idx + 1:02d}"
            priority, priority_reason = determine_detection_priority(det.raw_class)
            intel = DetectionIntelligence(
                priority=priority,
                priority_reason=priority_reason,
                review_status="PENDING REVIEW",
                evidence_status="AVAILABLE",
            )

            detections.append(
                AnalysisDetection(
                    id=det.detection_id,
                    code=code,
                    model=det.model,
                    class_id=det.class_id,
                    raw_class=det.raw_class,
                    display_class=det.display_class,
                    category=get_category_name(det.raw_class),
                    className=det.display_class.upper(),
                    type=det.display_class,
                    status="PENDING REVIEW",
                    priority=priority,
                    priority_reason=priority_reason,
                    review_status="PENDING REVIEW",
                    evidence_status="AVAILABLE",
                    intelligence=intel,
                    confidence=det.confidence,
                    confidence_percent=round(det.confidence * 100.0, 1),
                    bbox=AnalysisBoundingBox(
                        x1=det.x1,
                        y1=det.y1,
                        x2=det.x2,
                        y2=det.y2,
                        width=det.width,
                        height=det.height,
                        norm_x1=det.norm_x1,
                        norm_y1=det.norm_y1,
                        norm_w=det.norm_w,
                        norm_h=det.norm_h,
                        x=pct_x,
                        y=pct_y,
                        w=pct_w,
                        h=pct_h,
                    ),
                    survey_latitude=record.latitude if has_geo else None,
                    survey_longitude=record.longitude if has_geo else None,
                    has_target_geolocation=False,
                    target_geolocation_note=(
                        "Detection localized in sonar image-space with survey GPS anchor (towfish layback and acoustic slant-range ray tracing required for absolute seafloor coordinates)."
                        if has_geo
                        else "Image-only sonar input. No survey navigation metadata provided."
                    ),
                    geoLat=record.latitude if has_geo else None,
                    geoLon=record.longitude if has_geo else None,
                    latitude=record.latitude if has_geo else None,
                    longitude=record.longitude if has_geo else None,
                    coordinateReference="WGS 84 (Geographic 2D - EPSG:4326)" if has_geo else "UNAVAILABLE",
                    metadataSource="Survey Towfish GPS Anchor (Image-Space Detection)" if has_geo else "Image-only sonar input",
                    evidenceImage=evidence_url,
                    imagePosition={
                        "x": pct_x,
                        "y": pct_y,
                        "display": f"X: {round(pct_x)}%, Y: {round(pct_y)}%",
                    },
                    competing_hypotheses=getattr(det, "competing_hypotheses", None) or [],
                )
            )

        geolocation = AnalysisGeolocation(
            latitude=record.latitude,
            longitude=record.longitude,
            depth_m=record.depth_m,
            depth=record.depth_m,
            heading=record.heading,
            timestamp=record.timestamp,
            geolocation_available=has_geo,
        )

        survey_meta = AnalysisSurveyMetadata(
            latitude=record.latitude,
            longitude=record.longitude,
            depth=record.depth_m,
            heading=record.heading,
            timestamp=record.timestamp,
            geolocation_available=has_geo,
        )

        image_meta = AnalysisImageMetadata(
            filename=record.original_filename,
            width=record.image_width,
            height=record.image_height,
            channels=record.image_channels,
            format=record.image_format,
            size_bytes=record.image_size_bytes,
        )

        summary = compute_analysis_summary(
            detections=detections,
            models_executed=record.models_executed or [],
            execution_time_ms=record.execution_time_ms or 0.0,
        )

        return AnalysisDetailResponse(
            analysis_id=record.analysis_id,
            status=record.status,
            image=image_meta,
            geolocation=geolocation,
            metadata=survey_meta,
            detections=detections,
            summary=summary,
            triage=getattr(record, "triage", None),
            created_at=record.created_at,
            evidence=evidence_schema,
            evidence_url=evidence_url,
        )

    def get_analysis_by_id(self, analysis_id: str, db: Session) -> Optional[AnalysisDetailResponse]:
        """Fetch analysis details by analysis_id."""
        repo = AnalysisRepository(db)
        record = repo.get_by_analysis_id(analysis_id)
        if not record:
            return None
        return self.record_to_detail_response(record)

    def list_analyses(
        self,
        page: int,
        page_size: int,
        status: Optional[str],
        detection_type: Optional[str],
        db: Session,
    ) -> PaginatedAnalysisResponse:
        """Fetch paginated analyses list."""
        repo = AnalysisRepository(db)
        records, total = repo.list_analyses(
            page=page,
            page_size=page_size,
            status=status,
            detection_type=detection_type,
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        items = [self.record_to_detail_response(rec) for rec in records]

        return PaginatedAnalysisResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    def delete_analysis(self, analysis_id: str, db: Session) -> bool:
        """Delete analysis and associated evidence from DB and storage."""
        repo = AnalysisRepository(db)
        res = repo.delete_by_analysis_id(analysis_id)
        if not res:
            return False

        _, storage_path = res
        if storage_path:
            try:
                self.storage.delete_evidence(storage_path)
            except Exception as e:
                logger.warning(f"Failed to delete stored evidence for {analysis_id}: {e}")

        return True

    def get_evidence_file(self, analysis_id: str, db: Session) -> Tuple[bytes, str, str]:
        """Retrieve raw evidence image bytes, media type, and filename."""
        repo = AnalysisRepository(db)
        record = repo.get_by_analysis_id(analysis_id)
        if not record or not record.evidence:
            raise StorageError(f"Evidence record not found for analysis {analysis_id}")

        evidence = record.evidence
        data = self.storage.get_evidence(evidence.storage_path)
        return data, evidence.content_type, evidence.original_filename


analysis_persistence_service = AnalysisPersistenceService()

"""Analysis repository for managing analyses, detections, and evidence in the database."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.db_models import AnalysisRecord, DetectionRecord, EvidenceRecord

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """Repository layer for database operations on analyses, detections, and evidence."""

    def __init__(self, db: Session, owner_hash: Optional[str] = None):
        self.db = db
        self.owner_hash = owner_hash

    def create_analysis(
        self,
        analysis_data: Dict[str, Any],
        detections_data: List[Dict[str, Any]],
        evidence_data: Dict[str, Any],
    ) -> AnalysisRecord:
        """Atomically persist analysis, evidence metadata, and all detections.

        Rolls back the transaction if any part fails.
        """
        try:
            # 1. Create Analysis record
            record = AnalysisRecord(**analysis_data)
            self.db.add(record)
            self.db.flush()  # Ensures analysis_id constraint check / triggers

            # 2. Create Evidence metadata record
            evidence = EvidenceRecord(
                analysis_id=record.analysis_id,
                **evidence_data,
            )
            self.db.add(evidence)

            # 3. Create all Detection records
            for det in detections_data:
                det_record = DetectionRecord(
                    analysis_id=record.analysis_id,
                    **det,
                )
                self.db.add(det_record)

            self.db.commit()
            self.db.refresh(record)
            return record

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create analysis {analysis_data.get('analysis_id')}: {e}")
            raise

    def get_by_analysis_id(self, analysis_id: str) -> Optional[AnalysisRecord]:
        """Fetch a single analysis by its external analysis_id, including detections and evidence."""
        stmt = (
            select(AnalysisRecord)
            .where(AnalysisRecord.analysis_id == analysis_id)
            .options(
                selectinload(AnalysisRecord.detections),
                selectinload(AnalysisRecord.evidence),
            )
        )
        if self.owner_hash is not None:
            stmt = stmt.where(AnalysisRecord.owner_hash == self.owner_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_analyses(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        detection_type: Optional[str] = None,
    ) -> Tuple[List[AnalysisRecord], int]:
        """Retrieve paginated analyses with optional status and detection class filters."""
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        stmt = select(AnalysisRecord)
        if self.owner_hash is not None:
            stmt = stmt.where(AnalysisRecord.owner_hash == self.owner_hash)

        if status:
            stmt = stmt.where(AnalysisRecord.status == status)

        if detection_type:
            # Filter analyses containing at least one detection of this semantic or raw class
            det_subquery = (
                select(DetectionRecord.analysis_id)
                .where(
                    (DetectionRecord.display_class.ilike(f"%{detection_type}%"))
                    | (DetectionRecord.raw_class.ilike(f"%{detection_type}%"))
                )
                .scalar_subquery()
            )
            stmt = stmt.where(AnalysisRecord.analysis_id.in_(det_subquery))

        # Count total matching rows
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar() or 0

        # Fetch paginated items with eager loading
        stmt = (
            stmt.options(
                selectinload(AnalysisRecord.detections),
                selectinload(AnalysisRecord.evidence),
            )
            .order_by(AnalysisRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.execute(stmt).scalars().all())

        return items, total

    def delete_by_analysis_id(self, analysis_id: str) -> Optional[Tuple[AnalysisRecord, Optional[str]]]:
        """Delete an analysis and associated records from the database.

        Returns (record, storage_path) if found, else None.
        """
        record = self.get_by_analysis_id(analysis_id)
        if not record:
            return None

        storage_path = record.evidence.storage_path if record.evidence else None

        try:
            self.db.delete(record)
            self.db.commit()
            return record, storage_path
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete analysis {analysis_id}: {e}")
            raise

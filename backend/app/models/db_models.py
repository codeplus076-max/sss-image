"""SQLAlchemy database models for Side-Scan Sonar persistence."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class AnalysisRecord(Base):
    """Database model for Side-Scan Sonar analysis sessions."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    analysis_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)

    # Sonar Image Specifications
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    image_channels: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    image_format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    image_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Geolocation / Survey Navigation Metadata (WGS84 compatible, PostGIS extensible)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    heading: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Aggregated Summary & Metrics
    total_detections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    highest_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    models_executed: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    objects_by_type: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    triage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Audit Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Cascade Relationships
    detections: Mapped[List["DetectionRecord"]] = relationship(
        "DetectionRecord",
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="DetectionRecord.id",
    )
    evidence: Mapped[Optional["EvidenceRecord"]] = relationship(
        "EvidenceRecord",
        back_populates="analysis",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def geolocation_available(self) -> bool:
        """True if both latitude and longitude coordinates are present. Never fabricated."""
        return self.latitude is not None and self.longitude is not None

    @property
    def survey_metadata(self) -> dict:
        """Structured dictionary of survey navigation and sensor metadata."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "depth": self.depth_m,
            "heading": self.heading,
            "timestamp": self.timestamp,
            "geolocation_available": self.geolocation_available,
        }


class DetectionRecord(Base):
    """Database model for detected anomalies linked to an analysis."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    detection_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_class: Mapped[str] = mapped_column(String(64), nullable=False)
    display_class: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Pixel Coordinates
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)

    # Normalized Coordinates [0.0 - 1.0]
    norm_x1: Mapped[float] = mapped_column(Float, nullable=False)
    norm_y1: Mapped[float] = mapped_column(Float, nullable=False)
    norm_w: Mapped[float] = mapped_column(Float, nullable=False)
    norm_h: Mapped[float] = mapped_column(Float, nullable=False)

    # Multi-Model Competing Hypotheses
    competing_hypotheses: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Parent Relationship
    analysis: Mapped["AnalysisRecord"] = relationship(
        "AnalysisRecord",
        back_populates="detections",
    )


class EvidenceRecord(Base):
    """Database model for sonar evidence image metadata."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="image/png", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Parent Relationship
    analysis: Mapped["AnalysisRecord"] = relationship(
        "AnalysisRecord",
        back_populates="evidence",
    )

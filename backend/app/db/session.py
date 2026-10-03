"""Database engine and session management."""

import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

# Configure dialect-specific engine parameters
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    """Initialize database tables for current models and perform light auto-migrations."""
    try:
        # Import models so Base registers all mapped tables
        from app.models import db_models  # noqa: F401
        from sqlalchemy import inspect, text

        Base.metadata.create_all(bind=engine)

        # Auto-migrate missing columns for existing SQLite tables
        with engine.connect() as conn:
            inspector = inspect(engine)
            if "analyses" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("analyses")]
                if "triage" not in cols:
                    conn.execute(text("ALTER TABLE analyses ADD COLUMN triage JSON"))
                    conn.commit()
            if "detections" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("detections")]
                if "competing_hypotheses" not in cols:
                    conn.execute(text("ALTER TABLE detections ADD COLUMN competing_hypotheses JSON DEFAULT '[]'"))
                    conn.commit()

        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise


def get_db() -> Generator[Session, None, None]:
    """Dependency generator that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Ensure tables are created on module import
try:
    init_db()
except Exception as _e:
    logger.warning(f"Could not auto-initialize DB on import: {_e}")


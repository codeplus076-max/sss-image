"""
Root pytest configuration and environment setup for SIH26057 Sonar backend.
Sets single-threaded BLAS to avoid Windows OpenBLAS memory fragmentation during test suites.
Forces SQLite for local testing so psycopg2 / Supabase PostgreSQL is not required.
"""
import os

# ── Threading: prevent OpenBLAS / MKL from spawning multiple threads ──────────
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# ── Database: force SQLite for local tests (no psycopg2 needed) ───────────────
# Direct assignment overrides any .env file that pydantic-settings reads.
# This must appear BEFORE any app module import so session.py uses SQLite.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure database schema is created for SQLite test runs."""
    from app.db.session import init_db
    init_db()


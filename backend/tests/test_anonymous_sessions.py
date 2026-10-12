"""Exercise anonymous isolation through real HTTP routes and temporary storage."""
import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_application
from app.db.base import Base
from app.db.session import get_db
from app.core.config import settings
from app.core.anonymous_session import COOKIE_NAME
from app.schemas.analysis import AnalysisResponse, AnalysisImageMetadata, AnalysisSummary
from app.services.analysis_persistence_service import AnalysisPersistenceService
from app.services.storage_service import StorageService, LocalStorageProvider
from app.api.v1.routes import analysis


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def database():
        with sessions() as db:
            yield db
    app = create_application()
    app.dependency_overrides[get_db] = database
    service = AnalysisPersistenceService(StorageService(LocalStorageProvider(str(tmp_path))))
    monkeypatch.setattr(analysis, "analysis_persistence_service", service)
    monkeypatch.setattr("app.db.session.SessionLocal", sessions)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    monkeypatch.setattr(analysis.sonar_validator, "validate_upload", lambda **kwargs: None)
    def predict(**kwargs):
        return AnalysisResponse(
            analysis_id=str(uuid.uuid4()), status="completed",
            image=AnalysisImageMetadata(filename="survey.png", width=10, height=10),
            detections=[], summary=AnalysisSummary(total_detections=0, models_executed=[]),
        )
    monkeypatch.setattr(analysis.analysis_service, "analyze_sonar_image", predict)
    yield app, sessions, service, predict
    engine.dispose()


def test_browser_isolation_sync_async_and_legacy(isolated_app):
    app, sessions, service, predict = isolated_app
    a, b, stranger = [TestClient(app) for _ in range(3)]
    assert stranger.get("/api/v1/analysis").status_code == 401
    for client in (a, b):
        response = client.post("/api/v1/session")
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
    token = a.cookies.get(COOKIE_NAME)
    assert token != b.cookies.get(COOKIE_NAME)
    a.post("/api/v1/session")
    assert a.cookies.get(COOKIE_NAME) == token
    uploads = {"image": ("survey.png", b"image evidence", "image/png")}
    response = a.post("/api/v1/analysis/analyze", files=uploads)
    assert response.status_code == 200, response.text
    own_id = response.json()["analysis_id"]
    other = b.post("/api/v1/analysis/jobs", files=uploads)
    assert other.status_code == 202, other.text
    job_id = other.json()["job_id"]
    job = b.get(f"/api/v1/analysis/jobs/{job_id}")
    assert job.json()["status"] == "completed", job.text
    other_id = job.json()["result"]["analysis_id"]
    assert a.get(f"/api/v1/analysis/jobs/{job_id}").status_code == 404
    assert "owner_hash" not in job.json()
    with sessions() as db:
        from app.models.db_models import AnalysisRecord
        record = db.query(AnalysisRecord).filter_by(analysis_id=own_id).one()
        assert record.owner_hash == hashlib.sha256(token.encode()).hexdigest()
        legacy = predict()
        service.persist_analysis(legacy, b"legacy", "image/png", db)
    for client, allowed, denied in ((a, own_id, other_id), (b, other_id, own_id)):
        history = client.get("/api/v1/analysis?page_size=1")
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["analysis_id"] == allowed
        assert history.headers["cache-control"] == "private, no-store"
        assert client.get(f"/api/v1/analysis/{allowed}").status_code == 200
        assert client.get(f"/api/v1/analysis/{allowed}/evidence").content == b"image evidence"
        for denied_id in (denied, legacy.analysis_id):
            assert client.get(f"/api/v1/analysis/{denied_id}").status_code == 404
            assert client.get(f"/api/v1/analysis/{denied_id}/evidence").status_code == 404
            assert client.delete(f"/api/v1/analysis/{denied_id}").status_code == 404
    assert a.delete(f"/api/v1/analysis/{own_id}").status_code == 200
    assert a.get("/api/v1/analysis").json()["total"] == 0
    b.cookies.clear()
    assert b.get(f"/api/v1/analysis/{other_id}").status_code == 401
    b.post("/api/v1/session")
    assert b.get("/api/v1/analysis").json()["total"] == 0
    assert b.get(f"/api/v1/analysis/{other_id}").status_code == 404


def test_cookie_security_and_untrusted_origins(isolated_app):
    app, *_ = isolated_app
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/v1/session")
    assert "Secure" in response.headers["set-cookie"]
    assert "no-store" in response.headers["cache-control"]
    assert client.post("/api/v1/session", headers={"Origin": "https://attacker.vercel.app"}).status_code == 403
    response = client.options("/api/v1/analysis", headers={"Origin": "https://attacker.vercel.app", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in response.headers
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, "invalid")
    assert client.get("/api/v1/analysis").status_code == 401
    assert client.post("/api/v1/session").status_code == 200


def test_existing_database_migration(tmp_path, monkeypatch):
    from app.db import session
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE analyses (id INTEGER PRIMARY KEY, analysis_id VARCHAR(64), triage JSON)"))
        connection.execute(text("INSERT INTO analyses (analysis_id) VALUES ('old')"))
    monkeypatch.setattr(session, "engine", engine)
    session.init_db()
    session.init_db()
    assert "owner_hash" in {column["name"] for column in inspect(engine).get_columns("analyses")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT owner_hash FROM analyses WHERE analysis_id='old'")).scalar() is None
    engine.dispose()

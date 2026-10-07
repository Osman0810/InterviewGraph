from collections.abc import Generator

import pymupdf

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.dependencies import get_ai_provider_resolver
from app.ai.resolver import AIProviderResolver
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.api.routes.sessions import _sanitize_filename
from app.models.interview import InterviewSession


def _provider_resolver() -> AIProviderResolver:
    return AIProviderResolver(
        Settings(
            _env_file=None,
            gemini_api_key="test-gemini-key",
            openai_api_key="test-openai-key",
        )
    )


def test_creates_session_from_pasted_text() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ai_provider_resolver] = _provider_resolver
    try:
        response = TestClient(app).post(
            "/sessions",
            data={
                "job_description_text": "Build reliable APIs with Python.",
                "resume_text": "Built FastAPI services and PostgreSQL schemas.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["redirect_url"] == f"/session/{body['session_id']}/analysis"

    with Session(engine) as db:
        created_session = db.scalar(select(InterviewSession))
        assert created_session is not None
        assert created_session.job_description.raw_text.startswith("Build reliable")
        assert created_session.resume.extracted_text.startswith("Built FastAPI")
        assert created_session.resume.filename is None

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_filename_sanitization_removes_path_and_control_characters() -> None:
    assert _sanitize_filename("../../private résumé\x00.pdf") == "private_r_sum__.pdf"


def test_creates_session_from_validated_upload_inputs() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Built secure FastAPI services")
    resume_bytes = pdf.tobytes()
    pdf.close()

    def override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ai_provider_resolver] = _provider_resolver
    try:
        response = TestClient(app).post("/sessions", files={
            "job_description_file": ("role.txt", b"Python API engineer", "text/plain"),
            "resume_file": ("resume.pdf", resume_bytes, "application/pdf"),
        })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    with Session(engine) as db:
        session = db.scalar(select(InterviewSession))
        assert session.resume.filename == "resume.pdf"
        assert "FastAPI" in session.resume.extracted_text
    engine.dispose()

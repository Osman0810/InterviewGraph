from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.gemini_client import (
    GeminiProvider,
    GeminiProviderError,
    GeminiRateLimitError,
    GeminiServiceUnavailableError,
    GeminiStructuredResponseError,
    GeminiTimeoutError,
)
from app.ai.schemas.competency import CompetencyExtraction, CompetencyOutput
from app.ai.schemas.resume_analysis import ResumeEvidenceAnalysis, ResumeEvidenceOutput
from app.api.routes.analysis import get_jd_competency_service, get_resume_evidence_service
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import SessionMode
from app.models.interview import Competency, InterviewSession, JobDescription, Resume, ResumeEvidence
from app.services.jd_competency import JDCompetencyService
from app.services.resume_evidence import ResumeEvidenceService
from tests.fakes import FakeGeminiProvider


def competency(name: str, importance: int = 3) -> CompetencyOutput:
    return CompetencyOutput(
        name=name,
        category="Databases",
        description=f"{name} database capability",
        importance=importance,
        required_level="intermediate",
        jd_evidence=f"The JD mentions {name}",
        question_topics=["indexing"],
    )


def test_provider_uses_sdk_structured_output_without_network() -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = SimpleNamespace(
        text=CompetencyExtraction(competencies=[competency("PostgreSQL")]).model_dump_json()
    )
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=1,
        client=fake_client,
    )

    result = provider.generate_structured(
        prompt="A private job description", response_schema=CompetencyExtraction
    )

    assert result.competencies[0].name == "PostgreSQL"
    call = fake_client.models.generate_content.call_args
    assert call.kwargs["model"] == "test-model"
    assert call.kwargs["config"].response_json_schema == CompetencyExtraction.model_json_schema()
    assert call.kwargs["config"].response_mime_type == "application/json"


def test_provider_surfaces_quota_errors_without_network() -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = errors.ClientError(429, {})
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=1,
        client=fake_client,
    )

    with pytest.raises(GeminiRateLimitError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (SimpleNamespace(text=""), GeminiStructuredResponseError),
        (SimpleNamespace(text="{}"), GeminiStructuredResponseError),
    ],
)
def test_provider_rejects_empty_or_invalid_structured_output_without_network(response, expected_error) -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = response
    provider = GeminiProvider(api_key="test", model_name="test", timeout_ms=10, max_retries=1, client=fake_client)
    with pytest.raises(expected_error):
        provider.generate_structured(prompt="Private", response_schema=CompetencyExtraction)


def test_provider_maps_timeout_and_5xx_without_network() -> None:
    timeout_client = MagicMock()
    timeout_client.models.generate_content.side_effect = httpx.TimeoutException("timeout")
    provider = GeminiProvider(api_key="test", model_name="test", timeout_ms=10, max_retries=1, client=timeout_client)
    with pytest.raises(GeminiTimeoutError):
        provider.generate_structured(prompt="Private", response_schema=CompetencyExtraction)

    server_client = MagicMock()
    server_client.models.generate_content.side_effect = errors.ServerError(500, {})
    provider = GeminiProvider(api_key="test", model_name="test", timeout_ms=10, max_retries=1, client=server_client)
    with pytest.raises(GeminiServiceUnavailableError):
        provider.generate_structured(prompt="Private", response_schema=CompetencyExtraction)

    network_client = MagicMock()
    network_client.models.generate_content.side_effect = httpx.ConnectError("network blocked")
    provider = GeminiProvider(api_key="test", model_name="test", timeout_ms=10, max_retries=1, client=network_client)
    with pytest.raises(GeminiServiceUnavailableError):
        provider.generate_structured(prompt="Private", response_schema=CompetencyExtraction)


def test_provider_retries_503_with_bounded_exponential_backoff_and_jitter() -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = errors.ServerError(503, {})
    delays: list[float] = []
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=fake_client,
        sleep_fn=delays.append,
        jitter_fn=lambda _minimum, maximum: maximum,
    )

    with pytest.raises(GeminiServiceUnavailableError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert fake_client.models.generate_content.call_count == 3
    assert delays == [1.25, 2.5]


def test_provider_does_not_retry_rate_limit_or_non_retryable_client_errors() -> None:
    for error, expected_error in [
        (errors.ClientError(429, {}), GeminiRateLimitError),
        (errors.ClientError(401, {}), GeminiProviderError),
    ]:
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = error
        provider = GeminiProvider(
            api_key="test-key",
            model_name="test-model",
            timeout_ms=100,
            max_retries=3,
            client=fake_client,
            sleep_fn=lambda _delay: None,
        )

        with pytest.raises(expected_error):
            provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

        assert fake_client.models.generate_content.call_count == 1


def test_provider_does_not_retry_daily_or_project_quota_exhaustion() -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = errors.ClientError(
        429,
        {"error": {"message": "Daily project quota exhausted", "status": "RESOURCE_EXHAUSTED"}},
    )
    delays: list[float] = []
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=fake_client,
        sleep_fn=delays.append,
    )

    with pytest.raises(GeminiRateLimitError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert fake_client.models.generate_content.call_count == 1
    assert delays == []


def test_provider_retries_temporary_rate_limit_after_retry_after_delay() -> None:
    generated = CompetencyExtraction(competencies=[competency("Python")]).model_dump_json()
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [
        errors.ClientError(
            429,
            {"error": {"message": "Requests per minute exceeded", "status": "RESOURCE_EXHAUSTED"}},
            httpx.Response(429, headers={"Retry-After": "3"}),
        ),
        SimpleNamespace(text=generated),
    ]
    delays: list[float] = []
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=fake_client,
        sleep_fn=delays.append,
    )

    result = provider.generate_structured(
        prompt="Private prompt", response_schema=CompetencyExtraction
    )

    assert result.competencies[0].name == "Python"
    assert fake_client.models.generate_content.call_count == 2
    assert delays == [3.0]


def test_provider_retries_timeout_before_a_successful_response() -> None:
    generated = CompetencyExtraction(competencies=[competency("Python")]).model_dump_json()
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [
        httpx.TimeoutException("timeout"),
        SimpleNamespace(text=generated),
    ]
    delays: list[float] = []
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=fake_client,
        sleep_fn=delays.append,
        jitter_fn=lambda _minimum, _maximum: 0,
    )

    result = provider.generate_structured(
        prompt="Private prompt", response_schema=CompetencyExtraction
    )

    assert result.competencies[0].name == "Python"
    assert fake_client.models.generate_content.call_count == 2
    assert delays == [1]


def _analysis_error_response(error: Exception):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with Session(engine) as db:
        interview_session = InterviewSession(mode=SessionMode.INTERVIEW)
        interview_session.job_description = JobDescription(raw_text="Private job description")
        db.add(interview_session)
        db.commit()
        session_id = interview_session.id

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    service = MagicMock()
    service.extract_competencies.side_effect = error
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_jd_competency_service] = lambda: service
    try:
        from fastapi.testclient import TestClient

        response = TestClient(app).post(f"/sessions/{session_id}/analyze-jd")
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as db:
        competency_count = len(list(db.scalars(select(Competency))))
    Base.metadata.drop_all(engine)
    engine.dispose()
    return response, competency_count


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            GeminiServiceUnavailableError("secret prompt and test-key"),
            503,
            "AI service is temporarily unavailable. Please try again shortly.",
        ),
        (GeminiTimeoutError("secret prompt and test-key"), 504, "AI service timed out. Please try again."),
        (
            GeminiRateLimitError("secret prompt and test-key"),
            429,
            "AI service rate limit reached. Please try again later.",
        ),
        (
            GeminiStructuredResponseError("secret prompt and test-key"),
            502,
            "AI analysis returned an invalid structured result",
        ),
    ],
)
def test_analysis_route_maps_safe_provider_errors(error, expected_status, expected_detail) -> None:
    response, competency_count = _analysis_error_response(error)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "secret prompt" not in response.text
    assert "test-key" not in response.text
    assert competency_count == 0


def test_retries_do_not_duplicate_database_writes() -> None:
    generated = CompetencyExtraction(competencies=[competency("PostgreSQL")]).model_dump_json()
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [
        errors.ServerError(503, {}),
        errors.ServerError(503, {}),
        SimpleNamespace(text=generated),
    ]
    provider = GeminiProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=fake_client,
        sleep_fn=lambda _delay: None,
        jitter_fn=lambda _minimum, _maximum: 0,
    )
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with Session(engine) as db:
        interview_session = InterviewSession(mode=SessionMode.INTERVIEW)
        interview_session.job_description = JobDescription(raw_text="Private job description")
        db.add(interview_session)
        db.commit()
        session_id = interview_session.id

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_jd_competency_service] = lambda: JDCompetencyService(provider)
    try:
        from fastapi.testclient import TestClient

        response = TestClient(app).post(f"/sessions/{session_id}/analyze-jd")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert fake_client.models.generate_content.call_count == 3
    with Session(engine) as db:
        assert len(list(db.scalars(select(Competency)))) == 1
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_service_normalizes_postgres_and_postgresql() -> None:
    provider = MagicMock()
    provider.generate_structured.return_value = CompetencyExtraction(
        competencies=[competency("Postgres", 3), competency("PostgreSQL", 5)]
    )

    result = JDCompetencyService(provider).extract_competencies("A private job description")

    assert len(result) == 1
    assert result[0].name == "PostgreSQL"
    assert result[0].importance == 5


def test_fake_provider_replaces_production_provider_without_network() -> None:
    fake = FakeGeminiProvider([CompetencyExtraction(competencies=[competency("Python")])])
    result = JDCompetencyService(fake).extract_competencies("Private job description")
    assert result[0].name == "Python"
    assert len(fake.calls) == 1


def test_resume_service_analyzes_all_competencies_in_one_provider_call() -> None:
    provider = MagicMock()
    provider.generate_structured.return_value = ResumeEvidenceAnalysis(
        competency_evidence=[
            ResumeEvidenceOutput(
                competency_name="Postgres",
                evidence_found=True,
                evidence_strength=70,
                evidence=["Designed PostgreSQL schemas."],
                confidence=0.9,
                reasoning_summary="The résumé describes direct PostgreSQL work.",
            )
        ]
    )
    competency_item = SimpleNamespace(name="PostgreSQL", category="Databases", description="SQL", required_level="intermediate", jd_evidence="PostgreSQL")

    result = ResumeEvidenceService(provider).analyze(
        resume_text="Private résumé text", competencies=[competency_item]
    )

    assert len(result) == 1
    assert result[0].evidence_strength == 70
    assert provider.generate_structured.call_count == 1


def test_analysis_route_persists_mocked_competencies() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW)
        session.job_description = JobDescription(raw_text="PostgreSQL is required")
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    service = MagicMock()
    service.extract_competencies.return_value = [competency("PostgreSQL", 5)]
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_jd_competency_service] = lambda: service
    try:
        from fastapi.testclient import TestClient

        response = TestClient(app).post(f"/sessions/{session_id}/analyze-jd")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["competency_count"] == 1
    with Session(engine) as db:
        stored = db.scalar(select(Competency).where(Competency.session_id == session_id))
        assert stored is not None
        assert stored.name == "PostgreSQL"
        assert stored.question_topics == ["indexing"]

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_resume_analysis_route_persists_mocked_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW)
        session.job_description = JobDescription(raw_text="PostgreSQL is required")
        session.resume = Resume(extracted_text="Built PostgreSQL schemas.", file_type="text")
        session.competencies = [
            Competency(
                name="PostgreSQL",
                category="Databases",
                description="SQL database",
                importance=5,
                required_level="advanced",
                jd_evidence="PostgreSQL",
                question_topics=["indexing"],
            )
        ]
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    service = MagicMock()
    service.analyze.return_value = [
        ResumeEvidenceOutput(
            competency_name="PostgreSQL",
            evidence_found=True,
            evidence_strength=70,
            evidence=["Built PostgreSQL schemas."],
            confidence=0.9,
            reasoning_summary="The résumé describes direct database design work.",
        )
    ]
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_resume_evidence_service] = lambda: service
    try:
        from fastapi.testclient import TestClient

        response = TestClient(app).post(f"/sessions/{session_id}/analyze-resume")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["evidence_count"] == 1
    with Session(engine) as db:
        stored = db.scalar(select(ResumeEvidence))
        assert stored is not None
        assert stored.evidence == ["Built PostgreSQL schemas."]
        assert stored.reasoning_summary.startswith("The résumé")

    Base.metadata.drop_all(engine)
    engine.dispose()

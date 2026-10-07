from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.dependencies import get_ai_provider_resolver
from app.ai.schemas.competency import CompetencyExtraction, CompetencyOutput
from app.ai.schemas.evaluation import AnswerEvaluationOutput
from app.ai.schemas.question import QuestionOutput
from app.ai.schemas.resume_analysis import ResumeEvidenceAnalysis, ResumeEvidenceOutput
from app.ai.schemas.study_plan import StudyPlanOutput, StudyPlanTopic
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import GapPriority, QuestionType, ScoreSource, SessionMode, SessionStatus
from app.models.interview import (
    Answer,
    Competency,
    CompetencyScore,
    Evaluation,
    InterviewSession,
    JobDescription,
    Question,
    Resume,
    ResumeEvidence,
    StudyPlan,
)
from tests.fakes import FakeAIProvider


PROVIDERS = [
    pytest.param("gemini", "gemini-pinned-model", "google", id="gemini"),
    pytest.param("openai", "openai-pinned-model", "openai", id="openai"),
]


def _client_with_pinned_provider(
    engine, provider_name: str, model_name: str, fake_provider: FakeAIProvider
) -> tuple[TestClient, MagicMock]:
    factory = sessionmaker(bind=engine)
    resolver = MagicMock()
    resolver.resolve_pinned.return_value = fake_provider

    def db_dependency() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_ai_provider_resolver] = lambda: resolver
    return TestClient(app), resolver


def _new_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


@pytest.mark.parametrize(("provider_name", "model_name", "fake_provider_name"), PROVIDERS)
def test_jd_analysis_uses_session_pinned_provider(provider_name, model_name, fake_provider_name) -> None:
    engine = _new_engine()
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, ai_provider=provider_name, ai_model=model_name)
        session.job_description = JobDescription(raw_text="Python and FastAPI are required.")
        db.add(session)
        db.commit()
        session_id = session.id
    fake = FakeAIProvider(
        [CompetencyExtraction(competencies=[_competency()])],
        provider_name=fake_provider_name,
        model_name=model_name,
    )
    client, resolver = _client_with_pinned_provider(engine, provider_name, model_name, fake)
    try:
        response = client.post(f"/sessions/{session_id}/analyze-jd")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert resolver.resolve_pinned.call_args.args == (provider_name, model_name)
    assert len(fake.calls) == 1
    engine.dispose()


@pytest.mark.parametrize(("provider_name", "model_name", "fake_provider_name"), PROVIDERS)
def test_resume_analysis_uses_session_pinned_provider(provider_name, model_name, fake_provider_name) -> None:
    engine = _new_engine()
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, ai_provider=provider_name, ai_model=model_name)
        session.resume = Resume(extracted_text="Built FastAPI services.", file_type="text")
        session.competencies = [
            Competency(
                name="FastAPI", category="Backend", description="APIs", importance=4,
                required_level="intermediate", jd_evidence="FastAPI", question_topics=["routing"],
            )
        ]
        db.add(session)
        db.commit()
        session_id = session.id
    fake = FakeAIProvider(
        [
            ResumeEvidenceAnalysis(
                competency_evidence=[
                    ResumeEvidenceOutput(
                        competency_name="FastAPI", evidence_found=True, evidence_strength=70,
                        evidence=["Built FastAPI services."], confidence=0.8,
                        reasoning_summary="Direct project evidence.",
                    )
                ]
            )
        ],
        provider_name=fake_provider_name,
        model_name=model_name,
    )
    client, resolver = _client_with_pinned_provider(engine, provider_name, model_name, fake)
    try:
        response = client.post(f"/sessions/{session_id}/analyze-resume")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert resolver.resolve_pinned.call_args.args == (provider_name, model_name)
    assert len(fake.calls) == 1
    engine.dispose()


@pytest.mark.parametrize(("provider_name", "model_name", "fake_provider_name"), PROVIDERS)
def test_question_generation_uses_session_pinned_provider(provider_name, model_name, fake_provider_name) -> None:
    engine = _new_engine()
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, ai_provider=provider_name, ai_model=model_name)
        competency = Competency(
            name="RAG", category="Generative AI", description="Retrieval", importance=5,
            required_level="advanced", jd_evidence="Build RAG", question_topics=["retrieval"],
        )
        competency.resume_evidence = [
            ResumeEvidence(evidence_found=False, evidence_strength=0, evidence=[], confidence=0.5,
                           reasoning_summary="No evidence")
        ]
        session.competencies = [competency]
        db.add(session)
        db.commit()
        session_id = session.id
    fake = FakeAIProvider(
        [
            QuestionOutput(
                question="What does retrieval add to generation?", competency="RAG", difficulty=1,
                type="conceptual", expected_concepts=["grounding"], evaluation_rubric=["Explains grounding"],
            )
        ],
        provider_name=fake_provider_name,
        model_name=model_name,
    )
    client, resolver = _client_with_pinned_provider(engine, provider_name, model_name, fake)
    try:
        response = client.post(f"/sessions/{session_id}/interview/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert resolver.resolve_pinned.call_args.args == (provider_name, model_name)
    assert len(fake.calls) == 1
    engine.dispose()


@pytest.mark.parametrize(("provider_name", "model_name", "fake_provider_name"), PROVIDERS)
def test_answer_evaluation_uses_session_pinned_provider(provider_name, model_name, fake_provider_name) -> None:
    engine = _new_engine()
    with Session(engine) as db:
        session = InterviewSession(
            mode=SessionMode.INTERVIEW, status=SessionStatus.IN_PROGRESS,
            ai_provider=provider_name, ai_model=model_name,
        )
        competency = Competency(
            name="RAG", category="Generative AI", description="Retrieval", importance=5,
            required_level="advanced", jd_evidence="Build RAG", question_topics=["retrieval"],
        )
        competency.resume_evidence = [
            ResumeEvidence(evidence_found=True, evidence_strength=60, evidence=[], confidence=0.7,
                           reasoning_summary="Direct evidence")
        ]
        question = Question(
            competency=competency, question_text="Explain retrieval.", difficulty=1,
            question_type=QuestionType.CONCEPTUAL, sequence_number=1,
            expected_concepts=["grounding"], evaluation_rubric=["Explains grounding"],
        )
        session.competencies = [competency]
        session.questions = [question]
        db.add(session)
        db.commit()
        session_id, question_id = session.id, question.id
    fake = FakeAIProvider(
        [
            AnswerEvaluationOutput(
                correctness=80, completeness=70, practical_depth=65, communication=85, overall_score=75,
                strengths=["Clear"], missing_concepts=["metrics"], incorrect_claims=[], feedback="Good",
                suggested_better_answer_outline=["Explain metrics"],
            )
        ],
        provider_name=fake_provider_name,
        model_name=model_name,
    )
    client, resolver = _client_with_pinned_provider(engine, provider_name, model_name, fake)
    try:
        response = client.post(
            f"/sessions/{session_id}/questions/{question_id}/answer", json={"answer_text": "It grounds output."}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert resolver.resolve_pinned.call_args.args == (provider_name, model_name)
    with Session(engine) as db:
        evaluation = db.scalar(select(Evaluation))
        assert evaluation.ai_provider == fake_provider_name
        assert evaluation.model_name == model_name
    engine.dispose()


@pytest.mark.parametrize(("provider_name", "model_name", "fake_provider_name"), PROVIDERS)
def test_study_plan_generation_uses_session_pinned_provider(provider_name, model_name, fake_provider_name) -> None:
    engine = _new_engine()
    with Session(engine) as db:
        session = InterviewSession(
            mode=SessionMode.INTERVIEW, status=SessionStatus.COMPLETED,
            ai_provider=provider_name, ai_model=model_name,
        )
        competency = Competency(
            name="Vector Search", category="Generative AI", description="Retrieval", importance=5,
            required_level="advanced", jd_evidence="Vector databases", question_topics=["ANN"],
        )
        competency.resume_evidence = [
            ResumeEvidence(evidence_found=False, evidence_strength=20, evidence=[], confidence=0.6,
                           reasoning_summary="Limited evidence")
        ]
        competency.score = CompetencyScore(
            interview_score=50, resume_evidence_score=20, final_score=42.5, confidence=0.6,
            gap_priority=GapPriority.CRITICAL, score_source=ScoreSource.COMBINED,
        )
        session.competencies = [competency]
        db.add(session)
        db.commit()
        session_id = session.id
    fake = FakeAIProvider(
        [
            StudyPlanOutput(
                critical=[
                    StudyPlanTopic(
                        topic="Vector Search", priority="Critical", current_gap="Weak evidence",
                        learning_objectives=["Explain ANN"], concepts_to_review=["reranking"],
                        hands_on_task="Build semantic search", interview_questions_to_practice=["How does ANN work?"],
                        estimated_time_minutes=60,
                    )
                ]
            )
        ],
        provider_name=fake_provider_name,
        model_name=model_name,
    )
    client, resolver = _client_with_pinned_provider(engine, provider_name, model_name, fake)
    try:
        response = client.post(f"/sessions/{session_id}/study-plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert resolver.resolve_pinned.call_args.args == (provider_name, model_name)
    with Session(engine) as db:
        study_plan = db.scalar(select(StudyPlan))
        assert study_plan.ai_provider == fake_provider_name
        assert study_plan.model_name == model_name
    engine.dispose()


def _competency() -> CompetencyOutput:
    return CompetencyOutput(
        name="Python", category="Programming", description="Python engineering", importance=5,
        required_level="advanced", jd_evidence="Python is required.", question_topics=["typing"],
    )

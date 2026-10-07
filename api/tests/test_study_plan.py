from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.schemas.study_plan import StudyPlanOutput, StudyPlanTopic
from app.api.routes.study_plan import get_study_plan_service
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Answer, Competency, CompetencyScore, Evaluation, InterviewSession, Question, ResumeEvidence, StudyPlan
from app.models.enums import GapPriority, QuestionType, ScoreSource, SessionMode, SessionStatus
from app.services.study_plan import StudyPlanService


@pytest.fixture
def study_plan_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, status=SessionStatus.COMPLETED)
        competency = Competency(name="Vector Search", category="Generative AI", description="", importance=5,
                                required_level="advanced", jd_evidence="Vector database experience")
        competency.resume_evidence = [ResumeEvidence(evidence_found=False, evidence_strength=20, evidence=[],
                                                     confidence=.7, reasoning_summary="Little evidence")]
        competency.score = CompetencyScore(interview_score=50, resume_evidence_score=20, final_score=42.5,
                                           confidence=.6, gap_priority=GapPriority.CRITICAL,
                                           score_source=ScoreSource.COMBINED)
        question = Question(question_text="How do you tune ANN retrieval?", difficulty=3,
                            question_type=QuestionType.DEBUGGING, sequence_number=1,
                            expected_concepts=["private"], evaluation_rubric=["private"])
        answer = Answer(answer_text="CANDIDATE TRANSCRIPT MUST NOT BE SENT", skipped=False)
        answer.evaluation = Evaluation(correctness=50, completeness=40, practical_depth=45, communication=70,
                                       overall_score=50, strengths=[], missing_concepts=["reranking", "metadata filtering"],
                                       incorrect_claims=[], feedback="", structured_result={})
        question.answer = answer
        competency.questions = [question]
        session.competencies = [competency]
        session.questions = [question]
        db.add(session)
        db.commit()
        session_id = session.id

    output = StudyPlanOutput(critical=[StudyPlanTopic(
        topic="Vector Search", priority="Critical", current_gap="Weak ANN retrieval evidence.",
        learning_objectives=["Explain retrieval tradeoffs"], concepts_to_review=["ANN vs exact", "reranking"],
        hands_on_task="Build semantic search across 1,000 documents.",
        interview_questions_to_practice=["How do you choose top-k?"], estimated_time_minutes=120,
    )])
    provider = MagicMock()
    provider.provider_name = "google"
    provider.model_name = "test-model"
    provider.generate_structured.return_value = output
    service = StudyPlanService(provider)

    def db_dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_study_plan_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, session_id, provider, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_generates_targeted_plan_from_signals_and_persists_latest(study_plan_client):
    client, session_id, provider, engine = study_plan_client

    response = client.post(f"/sessions/{session_id}/study-plan")

    assert response.status_code == 200
    assert response.json()["plan"]["critical"][0]["topic"] == "Vector Search"
    assert provider.generate_structured.call_count == 1
    prompt = provider.generate_structured.call_args.kwargs["prompt"]
    assert "Vector Search" in prompt and "reranking" in prompt
    assert "CANDIDATE TRANSCRIPT MUST NOT BE SENT" not in prompt
    with Session(engine) as db:
        stored = db.scalar(select(StudyPlan))
        assert stored.generated_plan["critical"][0]["hands_on_task"].startswith("Build semantic")
        assert stored.ai_provider == "google"


def test_existing_plan_is_idempotent_but_regenerate_replaces_it(study_plan_client):
    client, session_id, provider, engine = study_plan_client
    first = client.post(f"/sessions/{session_id}/study-plan")
    second = client.post(f"/sessions/{session_id}/study-plan")
    regenerated = client.post(f"/sessions/{session_id}/study-plan/regenerate")

    assert first.status_code == second.status_code == regenerated.status_code == 200
    assert provider.generate_structured.call_count == 2
    with Session(engine) as db:
        assert len(list(db.scalars(select(StudyPlan)))) == 1


def test_rejects_a_topic_that_does_not_match_its_priority_group(study_plan_client):
    client, session_id, provider, _ = study_plan_client
    provider.generate_structured.return_value = StudyPlanOutput(important=[StudyPlanTopic(
        topic="Vector Search", priority="Critical", current_gap="Mismatch", learning_objectives=["Learn"],
        concepts_to_review=["ANN"], hands_on_task="Build it", interview_questions_to_practice=["Why?"],
        estimated_time_minutes=30,
    )])

    response = client.post(f"/sessions/{session_id}/study-plan")

    assert response.status_code == 409

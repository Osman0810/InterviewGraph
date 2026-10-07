from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import InterviewSession, Competency, ResumeEvidence, Question, Answer, Evaluation
from app.models.enums import SessionMode, SessionStatus, QuestionType
from app.ai.schemas.question import QuestionOutput
from app.ai.provider import AIStructuredResponseError, AITimeoutError
from app.services.question_generation import QuestionGenerator
from app.services.interview_engine import QuestionPlan
from app.services.interview import InterviewService
from app.api.routes.interview import get_interview_service


@pytest.fixture
def flow():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW)
        competency = Competency(name="RAG", category="Generative AI", description="Retrieval",
                               importance=5, required_level="advanced", jd_evidence="Build RAG")
        competency.resume_evidence = [ResumeEvidence(evidence_found=False, evidence_strength=0,
                                                    evidence=[], confidence=.5, reasoning_summary="No evidence")]
        session.competencies = [competency]
        db.add(session)
        db.commit()
        session_id = session.id
    provider = MagicMock()
    provider.generate_structured.return_value = QuestionOutput(
        question="What does retrieval add to generation?", competency="RAG", difficulty=1,
        type="conceptual", expected_concepts=["private-concept"], evaluation_rubric=["private-rubric"])
    service = InterviewService(QuestionGenerator(provider), question_limit=2)
    def db_dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_interview_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, session_id, provider, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_start_next_are_idempotent_and_private_fields_never_leave_api(flow):
    client, sid, provider, engine = flow
    first = client.post(f"/sessions/{sid}/interview/start")
    assert first.status_code == 200
    for response in [first, client.post(f"/sessions/{sid}/interview/start"),
                     client.get(f"/sessions/{sid}/interview/next-question")]:
        assert response.json()["question"]["id"] == first.json()["question"]["id"]
        assert "private-" not in response.text
        assert "expected_concepts" not in response.text and "evaluation_rubric" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert provider.generate_structured.call_count == 1
    with Session(engine) as db:
        q = db.scalar(select(Question))
        assert q.expected_concepts == ["private-concept"]
        assert q.evaluation_rubric == ["private-rubric"]


def test_evaluated_answer_advances_then_stops_after_final_skip(flow):
    client, sid, provider, engine = flow
    client.post(f"/sessions/{sid}/interview/start")
    with Session(engine) as db:
        q = db.scalar(select(Question))
        q.answer = Answer(answer_text="Retrieval grounds generation", skipped=False)
        db.commit()
    waiting = client.get(f"/sessions/{sid}/interview/next-question")
    assert waiting.json()["status"] == "awaiting_evaluation"
    assert provider.generate_structured.call_count == 1
    with Session(engine) as db:
        answer = db.scalar(select(Answer))
        answer.evaluation = Evaluation(correctness=90, completeness=90, practical_depth=90,
            communication=90, overall_score=90, feedback="Good")
        db.commit()
    provider.generate_structured.return_value = QuestionOutput(question="How would you implement retrieval?",
        competency="RAG", difficulty=2, type="implementation", expected_concepts=["index"],
        evaluation_rubric=["Correct indexing"])
    second = client.get(f"/sessions/{sid}/interview/next-question")
    assert second.json()["question"]["difficulty"] == 2
    with Session(engine) as db:
        q = db.scalar(select(Question).where(Question.sequence_number == 2))
        q.answer = Answer(skipped=True)
        db.commit()
    done = client.get(f"/sessions/{sid}/interview/next-question")
    assert done.json()["status"] == "completed" and done.json()["question"] is None
    assert provider.generate_structured.call_count == 2
    with Session(engine) as db:
        session = db.get(InterviewSession, sid)
        assert session.completed_at is not None and session.status == SessionStatus.COMPLETED


def test_invalid_state_and_unknown_session(flow):
    client, sid, provider, _ = flow
    assert client.get(f"/sessions/{sid}/interview/next-question").status_code == 409
    assert client.post(f"/sessions/{uuid4()}/interview/start").status_code == 404
    provider.generate_structured.assert_not_called()


def test_generation_failure_rolls_back_start(flow):
    client, sid, provider, engine = flow
    provider.generate_structured.side_effect = AITimeoutError("private provider detail")
    response = client.post(f"/sessions/{sid}/interview/start")
    assert response.status_code == 504 and "private" not in response.text
    with Session(engine) as db:
        assert db.get(InterviewSession, sid).status == SessionStatus.CREATED
        assert db.scalar(select(Question)) is None


@pytest.mark.parametrize("field,value", [("competency", "Python"), ("difficulty", 4), ("type", "system_design")])
def test_gemini_cannot_override_engine_plan(field, value):
    provider = MagicMock()
    result = dict(question="Explain RAG", competency="RAG", difficulty=1, type="conceptual",
                  expected_concepts=["retrieval"], evaluation_rubric=["Explains retrieval"])
    result[field] = value
    provider.generate_structured.return_value = QuestionOutput(**result)
    competency = SimpleNamespace(name="RAG", description="", jd_evidence="", question_topics=[])
    with pytest.raises(AIStructuredResponseError):
        QuestionGenerator(provider).generate(competency=competency,
            plan=QuestionPlan(uuid4(), 1, QuestionType.CONCEPTUAL), previous_questions=[])


def test_duplicate_question_rejected():
    provider = MagicMock()
    provider.generate_structured.return_value = QuestionOutput(question=" Explain RAG? ",
        competency="RAG", difficulty=1, type="conceptual",
        expected_concepts=["retrieval"], evaluation_rubric=["Explains retrieval"])
    competency = SimpleNamespace(name="RAG", description="", jd_evidence="", question_topics=[])
    with pytest.raises(AIStructuredResponseError, match="repeats"):
        QuestionGenerator(provider).generate(competency=competency,
            plan=QuestionPlan(uuid4(), 1, QuestionType.CONCEPTUAL), previous_questions=["Explain RAG."])

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.schemas.evaluation import AnswerEvaluationOutput
from app.api.routes.answers import get_answer_submission_service
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import QuestionType, SessionMode, SessionStatus
from app.models.interview import Competency, InterviewSession, Question, ResumeEvidence
from app.services.answer_evaluation import AnswerEvaluator
from app.services.answer_submission import AnswerSubmissionService


@pytest.fixture
def answer_flow():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(
            mode=SessionMode.INTERVIEW,
            status=SessionStatus.IN_PROGRESS,
            interview_question_limit=12,
        )
        competency = Competency(
            name="RAG",
            category="Generative AI",
            description="Retrieval augmented generation",
            importance=5,
            required_level="advanced",
            jd_evidence="Build RAG systems",
            question_topics=["retrieval"],
        )
        competency.resume_evidence = [
            ResumeEvidence(
                evidence_found=False,
                evidence_strength=0,
                evidence=[],
                confidence=0.5,
                reasoning_summary="No résumé evidence found.",
            )
        ]
        session.competencies = [competency]
        session.questions = [
            Question(
                competency=competency,
                question_text="What does retrieval add to generation?",
                difficulty=2,
                question_type=QuestionType.IMPLEMENTATION,
                sequence_number=1,
                expected_concepts=["private expected concept"],
                evaluation_rubric=["private rubric"],
            )
        ]
        db.add(session)
        db.commit()
        session_id, question_id = session.id, session.questions[0].id

    provider = MagicMock()
    provider.provider_name = "google"
    provider.model_name = "test-model"
    provider.generate_structured.return_value = AnswerEvaluationOutput(
        correctness=84,
        completeness=76,
        practical_depth=72,
        communication=91,
        overall_score=81,
        strengths=["Clearly explains grounded generation."],
        missing_concepts=["Describe how retrieval quality is measured."],
        incorrect_claims=[],
        feedback="Strong foundation. Add retrieval quality metrics next time.",
        suggested_better_answer_outline=["Define retrieval", "Explain grounding", "Mention metrics"],
    )
    service = AnswerSubmissionService(AnswerEvaluator(provider))

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_answer_submission_service] = lambda: service
    try:
        yield TestClient(app), session_id, question_id, provider, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_submitting_answer_persists_candidate_feedback_and_hides_private_context(answer_flow):
    client, session_id, question_id, provider, engine = answer_flow
    response = client.post(
        f"/sessions/{session_id}/questions/{question_id}/answer",
        json={"answer_text": "Retrieval supplies relevant context before generation."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_score"] == 81
    assert body["strengths"] == ["Clearly explains grounded generation."]
    assert body["missing_concepts"] == ["Describe how retrieval quality is measured."]
    assert "expected_concepts" not in body
    assert "evaluation_rubric" not in body
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert provider.generate_structured.call_count == 1

    with Session(engine) as db:
        question = db.get(Question, question_id)
        assert question.answer.answer_text.startswith("Retrieval supplies")
        assert question.answer.evaluation.overall_score == 81
        assert question.answer.evaluation.structured_result == {
            "suggested_better_answer_outline": ["Define retrieval", "Explain grounding", "Mention metrics"]
        }


def test_duplicate_answer_returns_saved_evaluation_without_second_gemini_call(answer_flow):
    client, session_id, question_id, provider, engine = answer_flow
    path = f"/sessions/{session_id}/questions/{question_id}/answer"
    first = client.post(path, json={"answer_text": "First answer."})
    second = client.post(path, json={"answer_text": "Second click answer."})

    assert first.status_code == second.status_code == 200
    assert second.headers["idempotent-replay"] == "true"
    assert second.json()["answer_id"] == first.json()["answer_id"]
    assert provider.generate_structured.call_count == 1
    with Session(engine) as db:
        assert db.scalar(select(Question)).answer.answer_text == "First answer."


def test_wrong_session_or_question_never_calls_gemini(answer_flow):
    client, session_id, question_id, provider, _ = answer_flow
    response = client.post(
        f"/sessions/{uuid4()}/questions/{question_id}/answer",
        json={"answer_text": "Answer"},
    )
    assert response.status_code == 404
    assert provider.generate_structured.call_count == 0

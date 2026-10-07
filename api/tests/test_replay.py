from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.schemas.evaluation import AnswerEvaluationOutput
from app.api.routes.replay import get_replay_service
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Answer, Competency, CompetencyScore, Evaluation, InterviewSession, Question, ReplayAttempt, ResumeEvidence
from app.models.enums import GapPriority, QuestionType, ScoreSource, SessionMode, SessionStatus
from app.services.answer_evaluation import AnswerEvaluator
from app.services.replay import ReplayService


@pytest.fixture
def replay_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, status=SessionStatus.COMPLETED)
        competency = Competency(name="RAG", category="Generative AI", description="", importance=5,
                                required_level="advanced", jd_evidence="Build RAG")
        competency.resume_evidence = [ResumeEvidence(evidence_found=True, evidence_strength=50, evidence=[], confidence=.7, reasoning_summary="Evidence")]
        competency.score = CompetencyScore(interview_score=48, resume_evidence_score=50, final_score=48.5,
                                           confidence=.7, gap_priority=GapPriority.HIGH, score_source=ScoreSource.COMBINED)
        question = Question(question_text="How would you improve retrieval quality?", difficulty=3,
                            question_type=QuestionType.DEBUGGING, sequence_number=1,
                            expected_concepts=["reranking"], evaluation_rubric=["mentions reranking"])
        answer = Answer(answer_text="Original weak answer", skipped=False)
        answer.evaluation = Evaluation(correctness=48, completeness=45, practical_depth=48, communication=65,
                                       overall_score=48, strengths=[], missing_concepts=["reranking", "metadata filtering"],
                                       incorrect_claims=[], feedback="Original feedback", structured_result={})
        question.answer = answer
        competency.questions = [question]
        session.competencies = [competency]
        session.questions = [question]
        db.add(session)
        db.commit()
        session_id, question_id = session.id, question.id

    provider = MagicMock()
    provider.provider_name = "google"
    provider.model_name = "test-model"
    provider.generate_structured.return_value = AnswerEvaluationOutput(
        correctness=80, completeness=78, practical_depth=82, communication=80, overall_score=79,
        strengths=["Explains retrieval tradeoffs"], missing_concepts=["metadata filtering"], incorrect_claims=[],
        feedback="Strongly improved answer.", suggested_better_answer_outline=["Define retrieval", "Explain reranking"],
    )
    service = ReplayService(AnswerEvaluator(provider))

    def db_dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_replay_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, session_id, question_id, provider, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_replay_uses_original_question_context_and_preserves_assessment(replay_client):
    client, session_id, question_id, provider, engine = replay_client

    response = client.post(f"/sessions/{session_id}/questions/{question_id}/replay", json={"answer_text": "Improved answer with reranking."})

    assert response.status_code == 200
    body = response.json()
    assert body["original_score"] == 48
    assert body["new_score"] == 79
    assert body["improvement"] == 31
    assert body["concepts_corrected"] == ["reranking"]
    assert body["concepts_still_missing"] == ["metadata filtering"]
    assert provider.generate_structured.call_count == 1
    with Session(engine) as db:
        original = db.scalar(select(Question)).answer.evaluation
        score = db.scalar(select(CompetencyScore))
        replay = db.scalar(select(ReplayAttempt))
        assert original.overall_score == 48 and original.feedback == "Original feedback"
        assert score.interview_score == 48 and score.final_score == 48.5
        assert replay.answer_text == "Improved answer with reranking."
        assert replay.evaluation["overall_score"] == 79


def test_replay_requires_completed_interview_and_never_calls_gemini(replay_client):
    client, session_id, question_id, provider, engine = replay_client
    with Session(engine) as db:
        db.get(InterviewSession, session_id).status = SessionStatus.IN_PROGRESS
        db.commit()

    response = client.post(f"/sessions/{session_id}/questions/{question_id}/replay", json={"answer_text": "Try again"})

    assert response.status_code == 409
    provider.generate_structured.assert_not_called()

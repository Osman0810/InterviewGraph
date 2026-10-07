import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Answer, Competency, CompetencyScore, Evaluation, InterviewSession, Question, ResumeEvidence
from app.models.enums import GapPriority, QuestionType, ScoreSource, SessionMode, SessionStatus


@pytest.fixture
def dashboard_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW, status=SessionStatus.COMPLETED)
        competency = Competency(name="System Design", category="Architecture", description="", importance=5,
                                required_level="advanced", jd_evidence="Design distributed systems")
        competency.resume_evidence = [ResumeEvidence(evidence_found=True, evidence_strength=60, evidence=["API work"],
                                                     confidence=.8, reasoning_summary="Evidence")]
        competency.score = CompetencyScore(interview_score=70, resume_evidence_score=60, final_score=67.5,
                                           confidence=.7, gap_priority=GapPriority.HIGH,
                                           score_source=ScoreSource.COMBINED)
        question = Question(question_text="How would you scale the API?", difficulty=4,
                            question_type=QuestionType.SYSTEM_DESIGN, sequence_number=1,
                            expected_concepts=["private concept"], evaluation_rubric=["private rubric"])
        answer = Answer(answer_text="I would use queues and replicas.", skipped=False)
        answer.evaluation = Evaluation(correctness=70, completeness=65, practical_depth=75, communication=80,
                                       overall_score=70, strengths=["Tradeoff awareness"],
                                       missing_concepts=["Backpressure"], incorrect_claims=[], feedback="Good",
                                       structured_result={"suggested_better_answer_outline": ["State load", "Add queue"]})
        question.answer = answer
        competency.questions = [question]
        session.competencies = [competency]
        session.questions = [question]
        db.add(session)
        db.commit()
        session_id = session.id

    def db_dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    try:
        with TestClient(app) as client:
            yield client, session_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_interview_results_are_read_only_projection_without_private_rubric(dashboard_client):
    client, session_id = dashboard_client

    response = client.get(f"/sessions/{session_id}/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "interview"
    assert payload["overall_readiness"] == 67.5
    assert payload["competencies"][0]["gap_priority"] == "high"
    feedback = payload["interview_feedback"][0]
    assert feedback["question"] == "How would you scale the API?"
    assert feedback["candidate_answer"] == "I would use queues and replicas."
    assert feedback["strengths"] == ["Tradeoff awareness"]
    assert feedback["missing_concepts"] == ["Backpressure"]
    assert feedback["improved_answer_outline"] == ["State load", "Add queue"]
    assert "private concept" not in response.text
    assert "private rubric" not in response.text
    assert response.headers["cache-control"] == "no-store"

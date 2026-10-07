from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Competency, CompetencyScore, InterviewSession, Question, ResumeEvidence
from app.models.enums import GapPriority, ScoreSource, SessionMode, SessionStatus


@pytest.fixture
def resume_only_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW)
        strong = Competency(name="Python", category="Programming", description="", importance=5,
                            required_level="advanced", jd_evidence="Python")
        strong.resume_evidence = [ResumeEvidence(evidence_found=True, evidence_strength=76, evidence=["Built APIs"],
                                                 confidence=.9, reasoning_summary="Demonstrated work")]
        gap = Competency(name="Kubernetes", category="DevOps", description="", importance=5,
                         required_level="advanced", jd_evidence="Kubernetes")
        gap.resume_evidence = [ResumeEvidence(evidence_found=False, evidence_strength=10, evidence=[],
                                              confidence=.7, reasoning_summary="No meaningful evidence")]
        session.competencies = [strong, gap]
        db.add(session)
        db.commit()
        session_id = session.id

    def db_dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    try:
        with TestClient(app) as client:
            yield client, session_id, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_resume_only_results_reuse_evidence_without_generating_questions(resume_only_client):
    client, session_id, engine = resume_only_client

    response = client.post(f"/sessions/{session_id}/resume-only")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "resume_only"
    assert body["label"] == "RESUME-BASED ANALYSIS"
    assert body["interview_feedback"] == []
    assert response.headers["cache-control"] == "no-store"
    assert {item["name"] for item in body["competencies"]} == {"Python", "Kubernetes"}
    kubernetes = next(item for item in body["competencies"] if item["name"] == "Kubernetes")
    assert kubernetes["resume_evidence_score"] == 10
    assert kubernetes["final_score"] == 10
    assert kubernetes["gap_priority"] == "critical"

    with Session(engine) as db:
        session = db.get(InterviewSession, session_id)
        scores = list(db.scalars(select(CompetencyScore)))
        assert session.mode == SessionMode.RESUME_ONLY
        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None
        assert len(scores) == 2
        assert all(score.interview_score is None and score.score_source == ScoreSource.RESUME_EVIDENCE for score in scores)
        assert db.scalar(select(Question)) is None


def test_resume_only_creation_is_idempotent_and_results_are_readable(resume_only_client):
    client, session_id, engine = resume_only_client
    first = client.post(f"/sessions/{session_id}/resume-only")
    second = client.post(f"/sessions/{session_id}/resume-only")
    fetched = client.get(f"/sessions/{session_id}/results")

    assert first.status_code == second.status_code == fetched.status_code == 200
    assert second.json() == first.json() == fetched.json()
    with Session(engine) as db:
        assert len(list(db.scalars(select(CompetencyScore)))) == 2


def test_started_interview_cannot_be_switched_to_resume_only(resume_only_client):
    client, session_id, engine = resume_only_client
    with Session(engine) as db:
        session = db.get(InterviewSession, session_id)
        session.status = SessionStatus.IN_PROGRESS
        db.commit()

    response = client.post(f"/sessions/{session_id}/resume-only")

    assert response.status_code == 409
    with Session(engine) as db:
        assert db.get(InterviewSession, session_id).mode == SessionMode.INTERVIEW
        assert db.scalar(select(CompetencyScore)) is None


def test_results_reject_unknown_or_non_resume_only_sessions(resume_only_client):
    client, session_id, _ = resume_only_client
    assert client.get(f"/sessions/{uuid4()}/results").status_code == 404
    assert client.get(f"/sessions/{session_id}/results").status_code == 409

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.gemini_client import GeminiProvider, GeminiStructuredResponseError
from app.ai.schemas.competency import CompetencyExtraction
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.core.rate_limit import InMemoryRateLimiter
from app.models import Answer, Competency, CompetencyScore, Evaluation, InterviewSession, JobDescription, Question, ReplayAttempt, Resume, ResumeEvidence, StudyPlan
from app.models.enums import GapPriority, QuestionType, ResumeFileType, ScoreSource, SessionMode


def test_blocked_gemini_response_is_reported_as_safe_structured_failure():
    client = type("Client", (), {"models": type("Models", (), {"generate_content": lambda *_args, **_kwargs: SimpleNamespace(parsed=None, candidates=[], prompt_feedback=SimpleNamespace(block_reason="SAFETY"))})()})()
    provider = GeminiProvider(api_key="test", model_name="test", timeout_ms=10, max_retries=1, client=client)

    try:
        provider.generate_structured(prompt="private", response_schema=CompetencyExtraction)
        assert False, "Expected structured failure"
    except GeminiStructuredResponseError as error:
        assert "private" not in str(error).lower()


def test_rate_limiter_returns_a_finite_retry_window():
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("client")[0] is True
    allowed, retry_after = limiter.allow("client")
    assert allowed is False and 1 <= retry_after <= 60


def test_delete_session_cascades_all_sensitive_records():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        session = InterviewSession(mode=SessionMode.INTERVIEW)
        session.job_description = JobDescription(raw_text="Private job description")
        session.resume = Resume(extracted_text="Private résumé", file_type=ResumeFileType.TEXT)
        competency = Competency(name="Python", category="Programming", description="", importance=5, required_level="advanced", jd_evidence="Python")
        competency.resume_evidence = [ResumeEvidence(evidence_found=True, evidence_strength=60, evidence=[], confidence=.8, reasoning_summary="Evidence")]
        competency.score = CompetencyScore(interview_score=50, resume_evidence_score=60, final_score=52.5, confidence=.7, gap_priority=GapPriority.HIGH, score_source=ScoreSource.COMBINED)
        question = Question(question_text="Private question", difficulty=2, question_type=QuestionType.IMPLEMENTATION, sequence_number=1, expected_concepts=[], evaluation_rubric=[])
        answer = Answer(answer_text="Private answer", skipped=False)
        answer.evaluation = Evaluation(correctness=50, completeness=50, practical_depth=50, communication=50, overall_score=50, feedback="Private feedback")
        question.answer = answer
        question.replay_attempts = [ReplayAttempt(original_answer=answer, answer_text="Replay", evaluation={"overall_score": 60})]
        competency.questions = [question]
        session.competencies = [competency]
        session.questions = [question]
        session.study_plan = StudyPlan(generated_plan={"critical": []})
        db.add(session)
        db.commit()
        session_id = session.id

    def db_dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    try:
        response = TestClient(app).delete(f"/sessions/{session_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    with Session(engine) as db:
        for model in (InterviewSession, JobDescription, Resume, Competency, ResumeEvidence, Question, Answer, Evaluation, CompetencyScore, StudyPlan, ReplayAttempt):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    engine.dispose()

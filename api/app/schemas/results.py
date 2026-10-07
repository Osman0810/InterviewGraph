from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import GapPriority, ScoreSource, SessionMode


class CompetencyResult(BaseModel):
    competency_id: UUID
    name: str
    category: str
    importance: int = Field(ge=1, le=5)
    resume_evidence_score: float = Field(ge=0, le=100)
    final_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    gap_priority: GapPriority
    score_source: ScoreSource


class ReplayAttemptResult(BaseModel):
    replay_id: UUID
    original_score: float = Field(ge=0, le=100)
    new_score: float = Field(ge=0, le=100)
    improvement: float
    concepts_corrected: list[str]
    concepts_still_missing: list[str]
    new_feedback: str
    improved_answer_outline: list[str]


class InterviewFeedbackResult(BaseModel):
    question_id: UUID
    competency_name: str
    question: str
    candidate_answer: str | None
    score: float = Field(ge=0, le=100)
    strengths: list[str]
    missing_concepts: list[str]
    improved_answer_outline: list[str]
    replay_attempts: list[ReplayAttemptResult]


class DashboardResults(BaseModel):
    session_id: UUID
    mode: SessionMode
    ai_provider: str | None = None
    label: str
    overall_readiness: float = Field(ge=0, le=100)
    overall_confidence: float = Field(ge=0, le=1)
    score_source: ScoreSource
    competencies: list[CompetencyResult]
    strengths: list[str]
    priority_gaps: list[str]
    interview_feedback: list[InterviewFeedbackResult]
    study_plan: dict | None


# Backwards-compatible name used by the resume-only creation route.
ResumeOnlyCompetencyResult = CompetencyResult
ResumeOnlyResults = DashboardResults

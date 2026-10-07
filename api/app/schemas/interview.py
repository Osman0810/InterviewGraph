from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    GapPriority,
    QuestionDifficulty,
    QuestionType,
    ResumeFileType,
    ScoreSource,
    SessionMode,
    SessionStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InterviewSessionCreate(BaseModel):
    mode: SessionMode
    status: SessionStatus = SessionStatus.CREATED


class InterviewSessionRead(ORMModel):
    id: UUID
    status: SessionStatus
    mode: SessionMode
    created_at: datetime
    completed_at: datetime | None


class SessionSubmissionResponse(BaseModel):
    session_id: UUID
    redirect_url: str


class JobDescriptionCreate(BaseModel):
    session_id: UUID
    raw_text: str
    company_name: str | None = None
    role_title: str | None = None


class JobDescriptionRead(JobDescriptionCreate, ORMModel):
    id: UUID


class ResumeCreate(BaseModel):
    session_id: UUID
    filename: str | None = None
    extracted_text: str
    file_type: ResumeFileType


class ResumeRead(ResumeCreate, ORMModel):
    id: UUID


class CompetencyCreate(BaseModel):
    session_id: UUID
    name: str
    category: str
    description: str
    importance: int = Field(ge=1, le=5)
    required_level: str
    jd_evidence: str
    question_topics: list[str] = Field(default_factory=list)


class CompetencyRead(CompetencyCreate, ORMModel):
    id: UUID


class ResumeEvidenceCreate(BaseModel):
    competency_id: UUID
    evidence_found: bool
    evidence_strength: int = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    confidence: float
    reasoning_summary: str


class ResumeEvidenceRead(ResumeEvidenceCreate, ORMModel):
    id: UUID


class QuestionCreate(BaseModel):
    session_id: UUID
    competency_id: UUID
    question_text: str
    difficulty: QuestionDifficulty
    question_type: QuestionType
    sequence_number: int = Field(ge=1)
    expected_concepts: list[str] = Field(default_factory=list)
    evaluation_rubric: list[str] = Field(default_factory=list)


class QuestionRead(QuestionCreate, ORMModel):
    id: UUID


class AnswerCreate(BaseModel):
    question_id: UUID
    answer_text: str | None = None
    skipped: bool = False


class AnswerRead(AnswerCreate, ORMModel):
    id: UUID
    submitted_at: datetime


class EvaluationCreate(BaseModel):
    answer_id: UUID
    correctness: float
    completeness: float
    practical_depth: float
    communication: float
    overall_score: float
    strengths: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    incorrect_claims: list[str] = Field(default_factory=list)
    feedback: str
    ai_provider: str | None = None
    model_name: str | None = None
    structured_result: dict[str, Any] | None = None


class EvaluationRead(EvaluationCreate, ORMModel):
    id: UUID


class CompetencyScoreCreate(BaseModel):
    competency_id: UUID
    interview_score: float | None = None
    resume_evidence_score: float
    final_score: float
    confidence: float
    gap_priority: GapPriority
    score_source: ScoreSource


class CompetencyScoreRead(CompetencyScoreCreate, ORMModel):
    id: UUID


class StudyPlanCreate(BaseModel):
    session_id: UUID
    generated_plan: dict[str, Any]
    ai_provider: str | None = None
    model_name: str | None = None
    structured_result: dict[str, Any] | None = None


class StudyPlanRead(StudyPlanCreate, ORMModel):
    id: UUID
    created_at: datetime


class ReplayAttemptCreate(BaseModel):
    question_id: UUID
    original_answer_id: UUID
    answer_text: str
    evaluation: dict[str, Any]
    ai_provider: str | None = None
    model_name: str | None = None
    structured_result: dict[str, Any] | None = None


class ReplayAttemptRead(ReplayAttemptCreate, ORMModel):
    id: UUID
    created_at: datetime

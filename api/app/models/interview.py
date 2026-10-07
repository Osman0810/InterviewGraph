from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    GapPriority,
    QuestionType,
    ResumeFileType,
    ScoreSource,
    SessionMode,
    SessionStatus,
)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", values_callable=lambda e: [v.value for v in e]), default=SessionStatus.CREATED, nullable=False
    )
    mode: Mapped[SessionMode] = mapped_column(Enum(SessionMode, name="session_mode", values_callable=lambda e: [v.value for v in e]), nullable=False)
    ai_provider: Mapped[str | None] = mapped_column(String(50))
    ai_model: Mapped[str | None] = mapped_column(String(255))
    interview_question_limit: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_description: Mapped[JobDescription | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    resume: Mapped[Resume | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    competencies: Mapped[list[Competency]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    study_plan: Mapped[StudyPlan | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    role_title: Mapped[str | None] = mapped_column(String(255))

    session: Mapped[InterviewSession] = relationship(back_populates="job_description")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    filename: Mapped[str | None] = mapped_column(String(512))
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[ResumeFileType] = mapped_column(
        Enum(ResumeFileType, name="resume_file_type", values_callable=lambda e: [v.value for v in e]), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(back_populates="resume")


class Competency(Base):
    __tablename__ = "competencies"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_competency_importance"),
        UniqueConstraint("session_id", "name", "category", name="uq_competency_session_name_category"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False)
    required_level: Mapped[str] = mapped_column(String(100), nullable=False)
    jd_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    question_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="competencies")
    resume_evidence: Mapped[list[ResumeEvidence]] = relationship(
        back_populates="competency", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(back_populates="competency")
    score: Mapped[CompetencyScore | None] = relationship(
        back_populates="competency", cascade="all, delete-orphan", uselist=False
    )


class ResumeEvidence(Base):
    __tablename__ = "resume_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_strength BETWEEN 0 AND 100", name="ck_resume_evidence_strength"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    competency_id: Mapped[UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    evidence_found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, nullable=False)

    competency: Mapped[Competency] = relationship(back_populates="resume_evidence")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_question_session_sequence"),
        CheckConstraint("difficulty BETWEEN 1 AND 4", name="ck_question_difficulty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    competency_id: Mapped[UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, values_callable=lambda e: [v.value for v in e]), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evaluation_rubric: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    diagnostic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="questions")
    competency: Mapped[Competency] = relationship(back_populates="questions")
    answer: Mapped[Answer | None] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )
    replay_attempts: Mapped[list[ReplayAttempt]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped[Question] = relationship(back_populates="answer")
    evaluation: Mapped[Evaluation | None] = relationship(
        back_populates="answer", cascade="all, delete-orphan", uselist=False
    )
    replay_attempts: Mapped[list[ReplayAttempt]] = relationship(back_populates="original_answer")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    correctness: Mapped[float] = mapped_column(Float, nullable=False)
    completeness: Mapped[float] = mapped_column(Float, nullable=False)
    practical_depth: Mapped[float] = mapped_column(Float, nullable=False)
    communication: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    missing_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    incorrect_claims: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    ai_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(255))
    structured_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    answer: Mapped[Answer] = relationship(back_populates="evaluation")


class CompetencyScore(Base):
    __tablename__ = "competency_scores"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    competency_id: Mapped[UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    interview_score: Mapped[float | None] = mapped_column(Float)
    resume_evidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    gap_priority: Mapped[GapPriority] = mapped_column(
        Enum(GapPriority, name="gap_priority", values_callable=lambda e: [v.value for v in e]), nullable=False
    )
    score_source: Mapped[ScoreSource] = mapped_column(
        Enum(ScoreSource, name="score_source", values_callable=lambda e: [v.value for v in e]), nullable=False
    )

    competency: Mapped[Competency] = relationship(back_populates="score")


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    generated_plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ai_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(255))
    structured_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    session: Mapped[InterviewSession] = relationship(back_populates="study_plan")


class ReplayAttempt(Base):
    __tablename__ = "replay_attempts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    original_answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ai_provider: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(255))
    structured_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    question: Mapped[Question] = relationship(back_populates="replay_attempts")
    original_answer: Mapped[Answer] = relationship(back_populates="replay_attempts")

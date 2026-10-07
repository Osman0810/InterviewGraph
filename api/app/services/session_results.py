"""Read-only dashboard projection from persisted PostgreSQL records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import GapPriority, SessionMode
from app.models.interview import Answer, Competency, InterviewSession, Question
from app.schemas.results import (
    CompetencyResult,
    DashboardResults,
    InterviewFeedbackResult,
    ReplayAttemptResult,
)
from app.services.scoring import ScoringService


class ResultsNotFound(ValueError):
    pass


class ResultsConflict(ValueError):
    pass


class SessionResultsService:
    """Only reads saved scores, answers, evaluations, and study-plan data."""

    def get(self, db: Session, session_id: UUID) -> DashboardResults:
        session = db.scalar(
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(
                selectinload(InterviewSession.competencies).selectinload(Competency.score),
                selectinload(InterviewSession.questions).selectinload(Question.competency),
                selectinload(InterviewSession.questions).selectinload(Question.answer)
                .selectinload(Answer.evaluation),
                selectinload(InterviewSession.questions).selectinload(Question.replay_attempts),
                selectinload(InterviewSession.study_plan),
            )
        )
        if session is None:
            raise ResultsNotFound("Session not found")
        if not session.competencies or any(competency.score is None for competency in session.competencies):
            raise ResultsConflict("Results have not been calculated for this session")
        return self.build(session)

    @staticmethod
    def build(session: InterviewSession) -> DashboardResults:
        competencies = sorted(
            session.competencies,
            key=lambda competency: (
                -SessionResultsService._priority_rank(competency.score.gap_priority),
                competency.score.final_score,
                -competency.importance,
                competency.name.casefold(),
            ),
        )
        results = [
            CompetencyResult(
                competency_id=competency.id,
                name=competency.name,
                category=competency.category,
                importance=competency.importance,
                resume_evidence_score=competency.score.resume_evidence_score,
                final_score=competency.score.final_score,
                confidence=competency.score.confidence,
                gap_priority=competency.score.gap_priority,
                score_source=competency.score.score_source,
            )
            for competency in competencies
        ]
        overall = ScoringService.calculate_overall(
            [(competency.importance, competency.score) for competency in competencies], mode=session.mode
        )
        feedback = [] if session.mode == SessionMode.RESUME_ONLY else SessionResultsService._feedback(session)
        return DashboardResults(
            session_id=session.id,
            mode=session.mode,
            ai_provider=session.ai_provider,
            label="RESUME-BASED ANALYSIS" if session.mode == SessionMode.RESUME_ONLY else "INTERVIEW RESULTS",
            overall_readiness=overall.overall_readiness,
            overall_confidence=overall.confidence,
            score_source=overall.score_source,
            competencies=results,
            strengths=[result.name for result in results if result.final_score >= 70],
            priority_gaps=[
                result.name for result in results
                if result.gap_priority in {GapPriority.CRITICAL, GapPriority.HIGH}
            ],
            interview_feedback=feedback,
            study_plan=session.study_plan.generated_plan if session.study_plan else None,
        )

    @staticmethod
    def _feedback(session: InterviewSession) -> list[InterviewFeedbackResult]:
        feedback: list[InterviewFeedbackResult] = []
        for question in sorted(session.questions, key=lambda item: item.sequence_number):
            if question.answer is None or question.answer.evaluation is None:
                continue
            evaluation = question.answer.evaluation
            stored_result = evaluation.structured_result if isinstance(evaluation.structured_result, dict) else {}
            outline = stored_result.get("suggested_better_answer_outline", [])
            feedback.append(InterviewFeedbackResult(
                question_id=question.id,
                competency_name=question.competency.name,
                question=question.question_text,
                candidate_answer=question.answer.answer_text,
                score=evaluation.overall_score,
                strengths=evaluation.strengths,
                missing_concepts=evaluation.missing_concepts,
                improved_answer_outline=[item for item in outline if isinstance(item, str)],
                replay_attempts=SessionResultsService._replays(question, evaluation.overall_score, evaluation.missing_concepts),
            ))
        return feedback

    @staticmethod
    def _replays(question: Question, original_score: float, original_missing: list[str]) -> list[ReplayAttemptResult]:
        attempts = []
        for replay in sorted(question.replay_attempts, key=lambda item: item.created_at):
            evaluation = replay.evaluation if isinstance(replay.evaluation, dict) else {}
            missing = [item for item in evaluation.get("missing_concepts", []) if isinstance(item, str)]
            remaining = {item.casefold() for item in missing}
            outline = replay.structured_result.get("suggested_better_answer_outline", []) if isinstance(replay.structured_result, dict) else []
            attempts.append(ReplayAttemptResult(
                replay_id=replay.id, original_score=original_score,
                new_score=float(evaluation.get("overall_score", 0)),
                improvement=round(float(evaluation.get("overall_score", 0)) - original_score, 2),
                concepts_corrected=[item for item in original_missing if item.casefold() not in remaining],
                concepts_still_missing=missing,
                new_feedback=str(evaluation.get("feedback", "")),
                improved_answer_outline=[item for item in outline if isinstance(item, str)],
            ))
        return attempts

    @staticmethod
    def _priority_rank(priority: GapPriority) -> int:
        return {
            GapPriority.CRITICAL: 4,
            GapPriority.HIGH: 3,
            GapPriority.MEDIUM: 2,
            GapPriority.LOW: 1,
        }[priority]

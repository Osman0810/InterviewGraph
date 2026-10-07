from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import SessionMode, SessionStatus
from app.models.interview import Answer, Evaluation, InterviewSession, Question
from app.schemas.answer import CandidateEvaluation
from app.services.answer_evaluation import AnswerEvaluator
from app.services.interview import InterviewConflict, InterviewNotFound
from app.services.scoring import ScoringService


class AnswerSubmissionService:
    """Serializes answer evaluation and returns an existing result for duplicates."""

    def __init__(self, evaluator: AnswerEvaluator) -> None:
        self._evaluator = evaluator

    def submit(
        self, db: Session, *, session_id: UUID, question_id: UUID, answer_text: str
    ) -> tuple[CandidateEvaluation, bool]:
        try:
            session = db.scalar(
                select(InterviewSession)
                .where(InterviewSession.id == session_id)
                .with_for_update()
            )
            if session is None:
                raise InterviewNotFound("Session not found")
            if session.mode != SessionMode.INTERVIEW or session.status != SessionStatus.IN_PROGRESS:
                raise InterviewConflict("Interview is not accepting answers")

            question = db.scalar(
                select(Question)
                .where(Question.id == question_id, Question.session_id == session_id)
                .options(
                    selectinload(Question.competency),
                    selectinload(Question.answer).selectinload(Answer.evaluation),
                )
                .with_for_update()
            )
            if question is None:
                raise InterviewNotFound("Question not found")
            if question.answer and question.answer.evaluation:
                return self._candidate_evaluation(question.answer, question.id), True
            if question.answer:
                raise InterviewConflict("Answer evaluation is already in progress")

            result = self._evaluator.evaluate(
                competency=question.competency,
                question=question,
                candidate_answer=answer_text,
            )
            answer = Answer(question_id=question.id, answer_text=answer_text, skipped=False)
            evaluation = Evaluation(
                correctness=result.correctness,
                completeness=result.completeness,
                practical_depth=result.practical_depth,
                communication=result.communication,
                overall_score=result.overall_score,
                strengths=result.strengths,
                missing_concepts=result.missing_concepts,
                incorrect_claims=result.incorrect_claims,
                feedback=result.feedback,
                ai_provider=self._evaluator.provider_name,
                model_name=self._evaluator.model_name,
                structured_result={
                    "suggested_better_answer_outline": result.suggested_better_answer_outline
                },
            )
            answer.evaluation = evaluation
            db.add(answer)
            db.flush()
            ScoringService().persist_session_scores(db, session.id)
            response = self._candidate_evaluation(answer, question.id)
            db.commit()
            return response, False
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _candidate_evaluation(answer: Answer, question_id: UUID) -> CandidateEvaluation:
        evaluation = answer.evaluation
        if evaluation is None:
            raise InterviewConflict("Answer has not been evaluated")
        outline = []
        if isinstance(evaluation.structured_result, dict):
            stored = evaluation.structured_result.get("suggested_better_answer_outline", [])
            if isinstance(stored, list):
                outline = [item for item in stored if isinstance(item, str)]
        return CandidateEvaluation(
            answer_id=answer.id,
            question_id=question_id,
            correctness=evaluation.correctness,
            completeness=evaluation.completeness,
            practical_depth=evaluation.practical_depth,
            communication=evaluation.communication,
            overall_score=evaluation.overall_score,
            strengths=evaluation.strengths,
            missing_concepts=evaluation.missing_concepts,
            incorrect_claims=evaluation.incorrect_claims,
            feedback=evaluation.feedback,
            suggested_better_answer_outline=outline,
        )

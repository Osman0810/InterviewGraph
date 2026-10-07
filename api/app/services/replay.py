"""Independent replay attempts that never alter the original assessment."""

from collections import defaultdict
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.schemas.evaluation import AnswerEvaluationOutput
from app.models.enums import SessionMode, SessionStatus
from app.models.interview import Answer, InterviewSession, Question, ReplayAttempt
from app.schemas.answer import ReplayEvaluation
from app.services.answer_evaluation import AnswerEvaluator
from app.services.interview import InterviewConflict, InterviewNotFound


class ReplayService:
    _locks: defaultdict[UUID, Lock] = defaultdict(Lock)

    def __init__(self, evaluator: AnswerEvaluator) -> None:
        self._evaluator = evaluator

    def submit(self, db: Session, *, session_id: UUID, question_id: UUID, answer_text: str) -> ReplayEvaluation:
        lock = self._locks[question_id]
        if not lock.acquire(blocking=False):
            raise InterviewConflict("A replay evaluation is already in progress")
        try:
            return self._submit_locked(db, session_id=session_id, question_id=question_id, answer_text=answer_text)
        finally:
            lock.release()

    def _submit_locked(self, db: Session, *, session_id: UUID, question_id: UUID, answer_text: str) -> ReplayEvaluation:
        try:
            session = db.scalar(select(InterviewSession).where(InterviewSession.id == session_id).with_for_update())
            if session is None:
                raise InterviewNotFound("Session not found")
            if session.mode != SessionMode.INTERVIEW or session.status != SessionStatus.COMPLETED:
                raise InterviewConflict("Replays are available after a completed interview")
            question = db.scalar(
                select(Question).where(Question.id == question_id, Question.session_id == session_id).options(
                    selectinload(Question.competency),
                    selectinload(Question.answer).selectinload(Answer.evaluation),
                ).with_for_update()
            )
            if question is None:
                raise InterviewNotFound("Question not found")
            if question.answer is None or question.answer.evaluation is None:
                raise InterviewConflict("This question has no evaluated original answer")
            original = question.answer.evaluation
            if original.overall_score >= 70 and not original.missing_concepts:
                raise InterviewConflict("Replays are available for questions that need review")

            result = self._evaluator.evaluate(competency=question.competency, question=question, candidate_answer=answer_text)
            replay = ReplayAttempt(
                question_id=question.id,
                original_answer_id=question.answer.id,
                answer_text=answer_text,
                evaluation=self._evaluation_payload(result),
                ai_provider=self._evaluator.provider_name,
                model_name=self._evaluator.model_name,
                structured_result={"suggested_better_answer_outline": result.suggested_better_answer_outline},
            )
            db.add(replay)
            db.flush()
            response = self._response(replay, original.overall_score, original.missing_concepts)
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _evaluation_payload(result: AnswerEvaluationOutput) -> dict[str, object]:
        return {
            "correctness": result.correctness, "completeness": result.completeness,
            "practical_depth": result.practical_depth, "communication": result.communication,
            "overall_score": result.overall_score, "strengths": result.strengths,
            "missing_concepts": result.missing_concepts, "incorrect_claims": result.incorrect_claims,
            "feedback": result.feedback,
        }

    @staticmethod
    def _response(replay: ReplayAttempt, original_score: float, original_missing: list[str]) -> ReplayEvaluation:
        evaluation = replay.evaluation
        missing = [item for item in evaluation.get("missing_concepts", []) if isinstance(item, str)]
        outline = []
        if isinstance(replay.structured_result, dict):
            outline = [item for item in replay.structured_result.get("suggested_better_answer_outline", []) if isinstance(item, str)]
        remaining = {item.casefold() for item in missing}
        corrected = [item for item in original_missing if item.casefold() not in remaining]
        return ReplayEvaluation(
            replay_id=replay.id, question_id=replay.question_id, original_score=original_score,
            new_score=float(evaluation["overall_score"]), improvement=round(float(evaluation["overall_score"]) - original_score, 2),
            concepts_corrected=corrected, concepts_still_missing=missing,
            new_feedback=str(evaluation["feedback"]), improved_answer_outline=outline,
        )

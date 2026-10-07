from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.models.interview import InterviewSession, Competency, Question, Answer
from app.models.enums import SessionMode, SessionStatus
from app.schemas.interview_flow import InterviewProgress, PublicQuestion
from app.services.interview_engine import InterviewEngine, CompetencyState, AskedQuestion
from app.services.question_generation import QuestionGenerator
from app.services.scoring import ScoringService


class InterviewNotFound(ValueError):
    pass


class InterviewConflict(ValueError):
    pass


class InterviewService:
    """Transaction owner; serializes generation per session with a PostgreSQL row lock."""

    def __init__(self, generator: QuestionGenerator, question_limit: int = 12):
        self.generator = generator
        self.question_limit = question_limit

    def advance(self, db: Session, session_id: UUID, *, start: bool = False) -> InterviewProgress:
        try:
            session = db.scalar(select(InterviewSession).where(
                InterviewSession.id == session_id
            ).with_for_update())
            if session is None:
                raise InterviewNotFound("Session not found")
            if session.status == SessionStatus.FAILED:
                raise InterviewConflict("Session has failed")
            if session.status == SessionStatus.CREATED:
                if not start:
                    raise InterviewConflict("Start the interview first")
                competencies = self._competencies(db, session_id)
                if not competencies or any(not c.resume_evidence for c in competencies):
                    raise InterviewConflict("Complete role and résumé analysis first")
                session.mode = SessionMode.INTERVIEW
                session.status = SessionStatus.IN_PROGRESS
                session.interview_question_limit = self.question_limit
            elif session.mode != SessionMode.INTERVIEW:
                raise InterviewConflict("Session is not in interview mode")
            limit = session.interview_question_limit or self.question_limit
            if session.status == SessionStatus.COMPLETED:
                result = InterviewProgress(status="completed", question_limit=limit)
            else:
                result = self._next(db, session, limit)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

    def end(self, db: Session, session_id: UUID) -> InterviewProgress:
        try:
            session = db.scalar(
                select(InterviewSession)
                .where(InterviewSession.id == session_id)
                .with_for_update()
            )
            if session is None:
                raise InterviewNotFound("Session not found")
            if session.mode != SessionMode.INTERVIEW:
                raise InterviewConflict("Session is not in interview mode")
            if session.status == SessionStatus.CREATED:
                raise InterviewConflict("Start the interview first")
            if session.status != SessionStatus.COMPLETED:
                session.status = SessionStatus.COMPLETED
                session.completed_at = datetime.now(timezone.utc)
            ScoringService().persist_session_scores(db, session.id)
            limit = session.interview_question_limit or self.question_limit
            db.commit()
            return InterviewProgress(status="completed", question_limit=limit)
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _competencies(db, session_id):
        return list(db.scalars(select(Competency).where(
            Competency.session_id == session_id
        ).options(selectinload(Competency.resume_evidence)).order_by(Competency.id)))

    def _next(self, db, session, limit):
        competencies = self._competencies(db, session.id)
        by_id = {c.id: c for c in competencies}
        questions = list(db.scalars(select(Question).where(
            Question.session_id == session.id
        ).options(selectinload(Question.answer).selectinload(Answer.evaluation))
          .order_by(Question.sequence_number)))
        history = []
        for q in questions:
            if q.answer is None:
                return self._response(q, by_id[q.competency_id], limit)
            if not q.answer.skipped and q.answer.evaluation is None:
                return InterviewProgress(status="awaiting_evaluation", question_limit=limit)
            score = 0 if q.answer.skipped else q.answer.evaluation.overall_score
            if not 0 <= score <= 100:
                raise InterviewConflict("Answer evaluation score must be between 0 and 100")
            history.append(AskedQuestion(q.competency_id, q.difficulty, q.question_type, score, q.diagnostic))
        states = [CompetencyState(c.id, c.name, c.importance,
                  c.resume_evidence[0].evidence_strength if c.resume_evidence else 0)
                  for c in competencies]
        plan = InterviewEngine(limit).next_plan(states, history)
        if plan is None:
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)
            ScoringService().persist_session_scores(db, session.id)
            return InterviewProgress(status="completed", question_limit=limit)
        competency = by_id[plan.competency_id]
        generated = self.generator.generate(
            competency=competency, plan=plan,
            previous_questions=[q.question_text for q in questions],
        )
        question = Question(
            session_id=session.id, competency_id=competency.id,
            question_text=generated.question, difficulty=plan.difficulty,
            question_type=plan.question_type, diagnostic=plan.diagnostic,
            sequence_number=max((q.sequence_number for q in questions), default=0) + 1,
            expected_concepts=generated.expected_concepts,
            evaluation_rubric=generated.evaluation_rubric,
        )
        db.add(question)
        db.flush()
        return self._response(question, competency, limit)

    @staticmethod
    def _response(question, competency, limit):
        return InterviewProgress(
            status="in_progress", question_limit=limit,
            question=PublicQuestion(
                id=question.id, competency_id=competency.id, competency=competency.name,
                question=question.question_text, difficulty=question.difficulty,
                type=question.question_type, sequence_number=question.sequence_number,
            ),
        )

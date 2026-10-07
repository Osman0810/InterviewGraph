"""Deterministic, evidence-only results for the no-interview pathway."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import SessionMode, SessionStatus
from app.models.interview import Competency, InterviewSession
from app.schemas.results import ResumeOnlyResults
from app.services.scoring import ScoringService
from app.services.session_results import ResultsConflict, SessionResultsService


class ResumeOnlyNotFound(ValueError):
    pass


class ResumeOnlyConflict(ValueError):
    pass


class ResumeOnlyResultsService:
    """Uses only persisted ResumeEvidence; it has no AI or question dependencies."""

    def create(self, db: Session, session_id: UUID) -> ResumeOnlyResults:
        try:
            session = self._load_session(db, session_id, lock=True)
            if session is None:
                raise ResumeOnlyNotFound("Session not found")
            if session.mode == SessionMode.RESUME_ONLY:
                return SessionResultsService().get(db, session_id)
            if session.status != SessionStatus.CREATED or session.questions:
                raise ResumeOnlyConflict("A started interview cannot be changed to résumé-only analysis")
            if not session.competencies:
                raise ResumeOnlyConflict("Complete role analysis before creating résumé-only results")
            if any(len(competency.resume_evidence) != 1 for competency in session.competencies):
                raise ResumeOnlyConflict("Complete résumé evidence analysis before creating results")

            session.mode = SessionMode.RESUME_ONLY
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.now(timezone.utc)
            ScoringService().persist_session_scores(db, session.id)
            db.commit()
            return SessionResultsService().get(db, session_id)
        except Exception:
            db.rollback()
            raise

    def get(self, db: Session, session_id: UUID) -> ResumeOnlyResults:
        session = self._load_session(db, session_id, lock=False)
        if session is None:
            raise ResumeOnlyNotFound("Session not found")
        if session.mode != SessionMode.RESUME_ONLY:
            raise ResumeOnlyConflict("Résumé-only results have not been created for this session")
        try:
            return SessionResultsService().get(db, session_id)
        except ResultsConflict as error:
            raise ResumeOnlyConflict("Résumé-only results are incomplete") from error

    @staticmethod
    def _load_session(db: Session, session_id: UUID, *, lock: bool) -> InterviewSession | None:
        statement = (
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(
                selectinload(InterviewSession.competencies).selectinload(Competency.resume_evidence),
                selectinload(InterviewSession.competencies).selectinload(Competency.score),
                selectinload(InterviewSession.questions),
            )
        )
        if lock:
            statement = statement.with_for_update()
        return db.scalar(statement)

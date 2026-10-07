from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.results import DashboardResults, ResumeOnlyResults
from app.services.resume_only_results import (
    ResumeOnlyConflict,
    ResumeOnlyNotFound,
    ResumeOnlyResultsService,
)
from app.services.session_results import ResultsConflict, ResultsNotFound, SessionResultsService

router = APIRouter(prefix="/sessions/{session_id}", tags=["results"])


@router.post("/resume-only", response_model=ResumeOnlyResults)
def create_resume_only_results(
    session_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
) -> ResumeOnlyResults:
    response.headers["Cache-Control"] = "no-store"
    try:
        return ResumeOnlyResultsService().create(db, session_id)
    except ResumeOnlyNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ResumeOnlyConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/results", response_model=DashboardResults)
def get_results(
    session_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
) -> DashboardResults:
    response.headers["Cache-Control"] = "no-store"
    try:
        return SessionResultsService().get(db, session_id)
    except ResultsNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ResultsConflict as error:
        raise HTTPException(409, str(error)) from error

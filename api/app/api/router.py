from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.routes.interview import router as interview_router
from app.api.routes.answers import router as answers_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.results import router as results_router
from app.api.routes.study_plan import router as study_plan_router
from app.api.routes.replay import router as replay_router


api_router = APIRouter()
api_router.include_router(interview_router)
api_router.include_router(answers_router)
api_router.include_router(analysis_router)
api_router.include_router(sessions_router)
api_router.include_router(results_router)
api_router.include_router(study_plan_router)
api_router.include_router(replay_router)


@api_router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error

    return {"status": "ok", "database": "connected"}

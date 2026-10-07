from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.ai.dependencies import get_session_ai_provider
from app.ai.provider import AIConfigurationError, AIProvider, AIProviderError, AIRateLimitError, AITimeoutError
from app.db.session import get_db
from app.schemas.study_plan import StudyPlanResponse
from app.services.study_plan import StudyPlanConflict, StudyPlanNotFound, StudyPlanService

router = APIRouter(prefix="/sessions/{session_id}/study-plan", tags=["study-plan"])


def get_study_plan_service(provider: AIProvider = Depends(get_session_ai_provider)) -> StudyPlanService:
    return StudyPlanService(provider)


def generate(session_id: UUID, response: Response, db: Session, service: StudyPlanService, *, regenerate: bool) -> StudyPlanResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return StudyPlanResponse(session_id=session_id, plan=service.generate(db, session_id, regenerate=regenerate))
    except StudyPlanNotFound as error:
        raise HTTPException(404, str(error)) from error
    except StudyPlanConflict as error:
        raise HTTPException(409, str(error)) from error
    except AIConfigurationError as error:
        raise HTTPException(503, "Study-plan generation is unavailable") from error
    except AIRateLimitError as error:
        raise HTTPException(429, "Study-plan generation is busy; try again shortly", headers={"Retry-After": "30"}) from error
    except AITimeoutError as error:
        raise HTTPException(504, "Study-plan generation timed out") from error
    except AIProviderError as error:
        raise HTTPException(502, "Could not generate a valid study plan") from error


@router.post("", response_model=StudyPlanResponse)
def create_study_plan(session_id: UUID, response: Response, db: Session = Depends(get_db), service: StudyPlanService = Depends(get_study_plan_service)) -> StudyPlanResponse:
    return generate(session_id, response, db, service, regenerate=False)


@router.post("/regenerate", response_model=StudyPlanResponse)
def regenerate_study_plan(session_id: UUID, response: Response, db: Session = Depends(get_db), service: StudyPlanService = Depends(get_study_plan_service)) -> StudyPlanResponse:
    return generate(session_id, response, db, service, regenerate=True)

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.ai.dependencies import get_session_ai_provider
from app.ai.provider import AIConfigurationError, AIProvider, AIProviderError, AIRateLimitError, AITimeoutError
from app.core.config import settings
from app.db.session import get_db
from app.schemas.interview_flow import InterviewProgress
from app.services.interview import InterviewService, InterviewConflict, InterviewNotFound
from app.services.question_generation import QuestionGenerator

router = APIRouter(prefix="/sessions/{session_id}/interview", tags=["interview"])


def get_interview_service(provider: AIProvider = Depends(get_session_ai_provider)):
    return InterviewService(QuestionGenerator(provider), settings.interview_question_limit)


def advance(service, db, session_id, start=False):
    try:
        return service.advance(db, session_id, start=start)
    except InterviewNotFound as error:
        raise HTTPException(404, str(error)) from error
    except InterviewConflict as error:
        raise HTTPException(409, str(error)) from error
    except AIConfigurationError as error:
        raise HTTPException(503, "Question generation is unavailable") from error
    except AIRateLimitError as error:
        raise HTTPException(429, "Question generation is busy; try again shortly",
                            headers={"Retry-After": "30"}) from error
    except AITimeoutError as error:
        raise HTTPException(504, "Question generation timed out") from error
    except AIProviderError as error:
        raise HTTPException(502, "Could not generate a valid question") from error


@router.post("/start", response_model=InterviewProgress)
def start_interview(session_id: UUID, response: Response, db: Session = Depends(get_db),
                    service: InterviewService = Depends(get_interview_service)):
    response.headers["Cache-Control"] = "no-store"
    return advance(service, db, session_id, start=True)


@router.get("/next-question", response_model=InterviewProgress)
def next_question(session_id: UUID, response: Response, db: Session = Depends(get_db),
                  service: InterviewService = Depends(get_interview_service)):
    response.headers["Cache-Control"] = "no-store"
    return advance(service, db, session_id)


@router.post("/end", response_model=InterviewProgress)
def end_interview(session_id: UUID, response: Response, db: Session = Depends(get_db),
                  service: InterviewService = Depends(get_interview_service)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.end(db, session_id)
    except InterviewNotFound as error:
        raise HTTPException(404, str(error)) from error
    except InterviewConflict as error:
        raise HTTPException(409, str(error)) from error

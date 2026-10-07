from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.ai.dependencies import get_session_ai_provider
from app.ai.provider import AIConfigurationError, AIProvider, AIProviderError, AIRateLimitError, AITimeoutError
from app.db.session import get_db
from app.schemas.answer import AnswerSubmission, CandidateEvaluation
from app.services.answer_evaluation import AnswerEvaluator
from app.services.answer_submission import AnswerSubmissionService
from app.services.interview import InterviewConflict, InterviewNotFound


router = APIRouter(prefix="/sessions/{session_id}/questions", tags=["answers"])


def get_answer_submission_service(
    provider: AIProvider = Depends(get_session_ai_provider),
) -> AnswerSubmissionService:
    return AnswerSubmissionService(AnswerEvaluator(provider))


@router.post("/{question_id}/answer", response_model=CandidateEvaluation)
def submit_answer(
    session_id: UUID,
    question_id: UUID,
    payload: AnswerSubmission,
    response: Response,
    db: Session = Depends(get_db),
    service: AnswerSubmissionService = Depends(get_answer_submission_service),
) -> CandidateEvaluation:
    response.headers["Cache-Control"] = "no-store"
    try:
        result, replayed = service.submit(
            db,
            session_id=session_id,
            question_id=question_id,
            answer_text=payload.answer_text,
        )
    except InterviewNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InterviewConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AIConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Answer evaluation is unavailable") from error
    except AIRateLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Answer evaluation is busy; try again shortly",
            headers={"Retry-After": "30"},
        ) from error
    except AITimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Answer evaluation timed out") from error
    except AIProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not evaluate this answer") from error

    if replayed:
        response.headers["Idempotent-Replay"] = "true"
    return result

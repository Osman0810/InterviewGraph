from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.ai.dependencies import get_session_ai_provider
from app.ai.provider import AIConfigurationError, AIProvider, AIProviderError, AIRateLimitError, AITimeoutError
from app.db.session import get_db
from app.schemas.answer import ReplayEvaluation, ReplaySubmission
from app.services.answer_evaluation import AnswerEvaluator
from app.services.interview import InterviewConflict, InterviewNotFound
from app.services.replay import ReplayService

router = APIRouter(prefix="/sessions/{session_id}/questions", tags=["replay"])


def get_replay_service(provider: AIProvider = Depends(get_session_ai_provider)) -> ReplayService:
    return ReplayService(AnswerEvaluator(provider))


@router.post("/{question_id}/replay", response_model=ReplayEvaluation)
def replay_answer(
    session_id: UUID, question_id: UUID, payload: ReplaySubmission, response: Response,
    db: Session = Depends(get_db), service: ReplayService = Depends(get_replay_service),
) -> ReplayEvaluation:
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.submit(db, session_id=session_id, question_id=question_id, answer_text=payload.answer_text)
    except InterviewNotFound as error:
        raise HTTPException(404, str(error)) from error
    except InterviewConflict as error:
        raise HTTPException(409, str(error)) from error
    except AIConfigurationError as error:
        raise HTTPException(503, "Replay evaluation is unavailable") from error
    except AIRateLimitError as error:
        raise HTTPException(429, "Replay evaluation is busy; try again shortly", headers={"Retry-After": "30"}) from error
    except AITimeoutError as error:
        raise HTTPException(504, "Replay evaluation timed out") from error
    except AIProviderError as error:
        raise HTTPException(502, "Could not evaluate the replay answer") from error

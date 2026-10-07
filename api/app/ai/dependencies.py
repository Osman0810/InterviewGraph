"""FastAPI dependencies for centralized session-pinned AI provider resolution."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.resolver import AIProviderResolver, UnsupportedAIProviderError
from app.ai.provider import AIProvider
from app.db.session import get_db
from app.models.interview import InterviewSession


def get_ai_provider_resolver() -> AIProviderResolver:
    return AIProviderResolver()


def get_session_ai_provider(
    session_id: UUID,
    db: Session = Depends(get_db),
    resolver: AIProviderResolver = Depends(get_ai_provider_resolver),
) -> AIProvider:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    try:
        return resolver.resolve_pinned(session.ai_provider, session.ai_model)
    except UnsupportedAIProviderError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session AI provider is invalid") from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session AI provider is unavailable",
        ) from error

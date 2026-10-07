from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.dependencies import get_session_ai_provider
from app.ai.provider import (
    AIConfigurationError,
    AIProvider,
    AIProviderError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AIStructuredResponseError,
    AITimeoutError,
)
from app.db.session import get_db
from app.models.interview import Competency, InterviewSession, ResumeEvidence
from app.services.jd_competency import JDCompetencyService
from app.services.resume_evidence import ResumeEvidenceService


router = APIRouter(prefix="/sessions", tags=["analysis"])


def get_jd_competency_service(
    provider: AIProvider = Depends(get_session_ai_provider),
) -> JDCompetencyService:
    return JDCompetencyService(provider)


def get_resume_evidence_service(
    provider: AIProvider = Depends(get_session_ai_provider),
) -> ResumeEvidenceService:
    return ResumeEvidenceService(provider)


@router.post("/{session_id}/analyze-jd", status_code=status.HTTP_201_CREATED)
def analyze_job_description(
    session_id: UUID,
    db: Session = Depends(get_db),
    service: JDCompetencyService = Depends(get_jd_competency_service),
) -> dict[str, object]:
    session = db.scalar(
        select(InterviewSession)
        .options(selectinload(InterviewSession.job_description))
        .where(InterviewSession.id == session_id)
    )
    if session is None or session.job_description is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        extracted = service.extract_competencies(session.job_description.raw_text)
    except AIConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service is temporarily unavailable. Please try again shortly.") from error
    except AIRateLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="AI service rate limit reached. Please try again later.") from error
    except AITimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI service timed out. Please try again.") from error
    except AIStructuredResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI analysis returned an invalid structured result") from error
    except AIServiceUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service is temporarily unavailable. Please try again shortly.") from error
    except AIProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI service request failed. Please try again shortly.") from error

    for competency in db.scalars(
        select(Competency).where(Competency.session_id == session.id)
    ):
        db.delete(competency)

    for competency in extracted:
        db.add(
            Competency(
                session_id=session.id,
                name=competency.name,
                category=competency.category,
                description=competency.description,
                importance=competency.importance,
                required_level=competency.required_level,
                jd_evidence=competency.jd_evidence,
                question_topics=competency.question_topics,
            )
        )
    db.commit()

    return {"session_id": str(session.id), "competency_count": len(extracted)}


@router.post("/{session_id}/analyze-resume", status_code=status.HTTP_201_CREATED)
def analyze_resume(
    session_id: UUID,
    db: Session = Depends(get_db),
    service: ResumeEvidenceService = Depends(get_resume_evidence_service),
) -> dict[str, object]:
    session = db.scalar(
        select(InterviewSession)
        .options(
            selectinload(InterviewSession.resume),
            selectinload(InterviewSession.competencies),
        )
        .where(InterviewSession.id == session_id)
    )
    if session is None or session.resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not session.competencies:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analyze the job description before the résumé",
        )

    try:
        evidence_results = service.analyze(
            resume_text=session.resume.extracted_text,
            competencies=session.competencies,
        )
    except AIConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service is temporarily unavailable. Please try again shortly.") from error
    except AIRateLimitError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="AI service rate limit reached. Please try again later.") from error
    except AITimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI service timed out. Please try again.") from error
    except AIStructuredResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI analysis returned an invalid structured result") from error
    except AIServiceUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service is temporarily unavailable. Please try again shortly.") from error
    except AIProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI service request failed. Please try again shortly.") from error

    existing_evidence = db.scalars(
        select(ResumeEvidence)
        .join(Competency)
        .where(Competency.session_id == session.id)
    )
    for item in existing_evidence:
        db.delete(item)
    db.flush()

    for competency, evidence in zip(session.competencies, evidence_results, strict=True):
        db.add(
            ResumeEvidence(
                competency_id=competency.id,
                evidence_found=evidence.evidence_found,
                evidence_strength=evidence.evidence_strength,
                evidence=evidence.evidence,
                confidence=evidence.confidence,
                reasoning_summary=evidence.reasoning_summary,
            )
        )
    db.commit()

    return {"session_id": str(session.id), "evidence_count": len(evidence_results)}


@router.get("/{session_id}/analysis-summary")
def get_analysis_summary(session_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    session = db.scalar(
        select(InterviewSession)
        .options(
            selectinload(InterviewSession.competencies).selectinload(Competency.resume_evidence)
        )
        .where(InterviewSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    competencies = [
        {"name": item.name, "importance": item.importance, "category": item.category}
        for item in session.competencies
    ]
    resume_analysis_complete = bool(competencies) and all(
        len(item.resume_evidence) == 1 for item in session.competencies
    )
    return {
        "session_id": str(session.id),
        "ai_provider": session.ai_provider,
        "competencies": competencies,
        "resume_analysis_complete": resume_analysis_complete,
    }

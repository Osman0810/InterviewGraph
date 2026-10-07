from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.dependencies import get_ai_provider_resolver
from app.ai.provider import AIConfigurationError
from app.ai.resolver import AIProviderResolver, UnsupportedAIProviderError
from app.db.session import get_db
from app.models.enums import ResumeFileType, SessionMode
from app.models.interview import InterviewSession, JobDescription, Resume
from app.parsers import DocumentParseError, extract_text
from app.schemas.interview import SessionSubmissionResponse


router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARACTERS = 200_000
MAX_DOCX_MEMBERS = 2_000
MAX_DOCX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
_UPLOAD_TYPES = {
    ".txt": (ResumeFileType.TEXT, {"text/plain"}),
    ".pdf": (ResumeFileType.PDF, {"application/pdf"}),
    ".docx": (
        ResumeFileType.DOCX,
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ),
}


def _sanitize_filename(filename: str | None) -> str:
    basename = Path(filename or "upload").name
    sanitized = _FILENAME_PATTERN.sub("_", basename).strip("._")
    return (sanitized or "upload")[:180]


def _validate_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_MEMBERS or sum(item.file_size for item in members) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=413, detail="DOCX content is too large")
            if "[Content_Types].xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                raise HTTPException(status_code=422, detail="Invalid DOCX file")
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=422, detail="Invalid DOCX file") from error


async def _read_upload(
    upload: UploadFile, allowed_extensions: set[str]
) -> tuple[str, ResumeFileType, bytes]:
    filename = _sanitize_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions or extension not in _UPLOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    file_type, allowed_media_types = _UPLOAD_TYPES[extension]
    content_type = (upload.content_type or "").lower()
    if content_type not in allowed_media_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file MIME type does not match the selected document type",
        )

    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Files must be 5 MB or smaller")
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is empty")

    if file_type is ResumeFileType.PDF and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid PDF file")
    if file_type is ResumeFileType.DOCX:
        if not zipfile.is_zipfile(BytesIO(content)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid DOCX file")
        _validate_docx_archive(content)

    return filename, file_type, content


def _validate_pasted_text(value: str | None, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} text is required",
        )
    if len(text) > MAX_TEXT_CHARACTERS:
        raise HTTPException(status_code=413, detail=f"{label} text is too large")
    return text


async def _resolve_text_source(
    pasted_text: str | None,
    upload: UploadFile | None,
    label: str,
    allowed_extensions: set[str],
) -> tuple[str, str | None, ResumeFileType]:
    has_text = bool((pasted_text or "").strip())
    if has_text == (upload is not None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Provide exactly one {label} input: pasted text or an uploaded file",
        )

    if has_text:
        return _validate_pasted_text(pasted_text, label), None, ResumeFileType.TEXT

    assert upload is not None
    filename, file_type, content = await _read_upload(upload, allowed_extensions)
    try:
        extracted = extract_text(content, file_type)
        if len(extracted) > MAX_TEXT_CHARACTERS:
            raise HTTPException(status_code=413, detail=f"{label} text is too large")
        return extracted, filename, file_type
    except DocumentParseError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("", response_model=SessionSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    job_description_text: str | None = Form(default=None),
    job_description_file: UploadFile | None = File(default=None),
    resume_text: str | None = Form(default=None),
    resume_file: UploadFile | None = File(default=None),
    mode: SessionMode = Form(default=SessionMode.INTERVIEW),
    ai_provider: str | None = Form(default=None),
    db: Session = Depends(get_db),
    provider_resolver: AIProviderResolver = Depends(get_ai_provider_resolver),
) -> SessionSubmissionResponse:
    """Create a session from in-memory source files; original uploads are never persisted."""

    jd_text, _, _ = await _resolve_text_source(
        job_description_text,
        job_description_file,
        "Job description",
        {".txt"},
    )
    resume_extracted_text, resume_filename, resume_file_type = await _resolve_text_source(
        resume_text,
        resume_file,
        "Résumé",
        {".pdf", ".docx"},
    )

    try:
        selection = provider_resolver.select_for_new_session(ai_provider)
    except UnsupportedAIProviderError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported AI provider") from error
    except AIConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Selected AI provider is unavailable") from error

    session = InterviewSession(
        mode=mode,
        ai_provider=selection.provider_name,
        ai_model=selection.model_name,
    )
    session.job_description = JobDescription(raw_text=jd_text)
    session.resume = Resume(
        filename=resume_filename,
        extracted_text=resume_extracted_text,
        file_type=resume_file_type,
    )
    try:
        db.add(session)
        db.commit()
        db.refresh(session)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Session storage is temporarily unavailable") from error

    return SessionSubmissionResponse(
        session_id=session.id,
        redirect_url=f"/session/{session.id}/analysis",
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: UUID, db: Session = Depends(get_db)) -> None:
    """Erase the session and every cascading related record, including source text."""
    session = db.scalar(select(InterviewSession).where(InterviewSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        db.delete(session)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Session deletion is temporarily unavailable") from error

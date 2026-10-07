from __future__ import annotations

from io import BytesIO

import pymupdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.models.enums import ResumeFileType


class DocumentParseError(ValueError):
    """Raised when an uploaded document cannot safely be read as text."""


def extract_text(content: bytes, file_type: ResumeFileType) -> str:
    """Extract plain text from an in-memory resume or job-description document."""

    try:
        if file_type is ResumeFileType.PDF:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                text = "\n".join(page.get_text() for page in document)
        elif file_type is ResumeFileType.DOCX:
            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        elif file_type is ResumeFileType.TEXT:
            text = content.decode("utf-8-sig")
        else:
            raise DocumentParseError("Unsupported document type")
    except (
        pymupdf.FileDataError,
        PackageNotFoundError,
        UnicodeDecodeError,
        ValueError,
        OSError,
    ) as error:
        raise DocumentParseError("The uploaded file could not be parsed") from error

    cleaned_text = text.strip()
    if not cleaned_text:
        raise DocumentParseError("The uploaded document does not contain readable text")

    return cleaned_text

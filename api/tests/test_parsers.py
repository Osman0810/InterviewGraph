from io import BytesIO

import pymupdf
import pytest
from docx import Document

from app.models.enums import ResumeFileType
from app.parsers import DocumentParseError, extract_text


def test_extracts_text_from_pdf() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Python and PostgreSQL")
    content = document.tobytes()
    document.close()

    assert extract_text(content, ResumeFileType.PDF) == "Python and PostgreSQL"


def test_extracts_text_from_docx() -> None:
    document = Document()
    document.add_paragraph("FastAPI and distributed systems")
    buffer = BytesIO()
    document.save(buffer)

    assert extract_text(buffer.getvalue(), ResumeFileType.DOCX) == "FastAPI and distributed systems"


def test_extracts_utf8_text() -> None:
    assert extract_text("Résumé text".encode("utf-8"), ResumeFileType.TEXT) == "Résumé text"


def test_rejects_empty_text_document() -> None:
    with pytest.raises(DocumentParseError, match="does not contain readable text"):
        extract_text(b"\n\n", ResumeFileType.TEXT)


def test_rejects_invalid_pdf() -> None:
    with pytest.raises(DocumentParseError, match="could not be parsed"):
        extract_text(b"not a PDF", ResumeFileType.PDF)

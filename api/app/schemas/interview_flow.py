from typing import Literal
from uuid import UUID
from pydantic import BaseModel
from app.models.enums import QuestionType


class PublicQuestion(BaseModel):
    """Explicit allowlist; never serialize private scoring fields."""
    id: UUID
    competency_id: UUID
    competency: str
    question: str
    difficulty: int
    type: QuestionType
    sequence_number: int


class InterviewProgress(BaseModel):
    status: Literal["in_progress", "awaiting_evaluation", "completed"]
    question_limit: int
    question: PublicQuestion | None = None

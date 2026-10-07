from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import QuestionType


class QuestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=8000)
    competency: str = Field(min_length=1)
    difficulty: int = Field(ge=1, le=4)
    type: QuestionType
    expected_concepts: list[str] = Field(min_length=1)
    evaluation_rubric: list[str] = Field(min_length=1)

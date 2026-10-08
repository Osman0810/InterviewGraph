from pydantic import BaseModel, ConfigDict, Field


class AnswerEvaluationOutput(BaseModel):
    """Concise, candidate-facing evaluation with no private reasoning trace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correctness: float = Field(ge=0, le=100)
    completeness: float = Field(ge=0, le=100)
    practical_depth: float = Field(ge=0, le=100)
    communication: float = Field(ge=0, le=100)
    overall_score: float = Field(ge=0, le=100)
    strengths: list[str] = Field(max_length=5)
    missing_concepts: list[str] = Field(max_length=5)
    incorrect_claims: list[str] = Field(max_length=5)
    feedback: str = Field(min_length=1, max_length=1000)
    suggested_better_answer_outline: list[str] = Field(max_length=6)

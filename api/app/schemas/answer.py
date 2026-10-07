from uuid import UUID

from pydantic import BaseModel, Field


class AnswerSubmission(BaseModel):
    answer_text: str = Field(min_length=1, max_length=20_000)


class CandidateEvaluation(BaseModel):
    answer_id: UUID
    question_id: UUID
    correctness: float
    completeness: float
    practical_depth: float
    communication: float
    overall_score: float
    strengths: list[str]
    missing_concepts: list[str]
    incorrect_claims: list[str]
    feedback: str
    suggested_better_answer_outline: list[str]
    next_question_ready: bool = True


class ReplaySubmission(BaseModel):
    answer_text: str = Field(min_length=1, max_length=20_000)


class ReplayEvaluation(BaseModel):
    replay_id: UUID
    question_id: UUID
    original_score: float = Field(ge=0, le=100)
    new_score: float = Field(ge=0, le=100)
    improvement: float
    concepts_corrected: list[str]
    concepts_still_missing: list[str]
    new_feedback: str
    improved_answer_outline: list[str]

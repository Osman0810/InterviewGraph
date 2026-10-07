from typing import Literal

from pydantic import BaseModel, Field


class StudyPlanTopic(BaseModel):
    topic: str = Field(min_length=1, max_length=160)
    priority: Literal["Critical", "Important", "Optional"]
    current_gap: str = Field(min_length=1, max_length=800)
    learning_objectives: list[str] = Field(min_length=1, max_length=6)
    concepts_to_review: list[str] = Field(min_length=1, max_length=8)
    hands_on_task: str = Field(min_length=1, max_length=800)
    interview_questions_to_practice: list[str] = Field(min_length=1, max_length=5)
    estimated_time_minutes: int = Field(ge=15, le=2_400)


class StudyPlanOutput(BaseModel):
    critical: list[StudyPlanTopic] = Field(default_factory=list)
    important: list[StudyPlanTopic] = Field(default_factory=list)
    optional: list[StudyPlanTopic] = Field(default_factory=list)

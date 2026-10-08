from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StudyPlanTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=160)
    priority: Literal["Critical", "Important", "Optional"]
    current_gap: str = Field(min_length=1, max_length=800)
    learning_objectives: list[str] = Field(min_length=1, max_length=6)
    concepts_to_review: list[str] = Field(min_length=1, max_length=8)
    hands_on_task: str = Field(min_length=1, max_length=800)
    interview_questions_to_practice: list[str] = Field(min_length=1, max_length=5)
    estimated_time_minutes: int = Field(ge=15, le=2_400)


class StudyPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical: list[StudyPlanTopic]
    important: list[StudyPlanTopic]
    optional: list[StudyPlanTopic]

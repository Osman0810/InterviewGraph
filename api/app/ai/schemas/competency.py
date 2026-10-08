from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CompetencyCategory = Literal[
    "Programming",
    "Backend",
    "Frontend",
    "Databases",
    "Cloud",
    "DevOps",
    "Machine Learning",
    "Generative AI",
    "Data Engineering",
    "Security",
    "Architecture",
    "Testing",
    "Domain Knowledge",
    "Communication",
]
RequiredLevel = Literal["beginner", "intermediate", "advanced", "expert"]


class CompetencyOutput(BaseModel):
    """A competency directly supported by the submitted job description."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    category: CompetencyCategory
    description: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)
    required_level: RequiredLevel
    jd_evidence: str = Field(min_length=1)
    question_topics: list[str]


class CompetencyExtraction(BaseModel):
    """Structured JD analysis result returned by Gemini."""

    model_config = ConfigDict(extra="forbid")

    competencies: list[CompetencyOutput] = Field(min_length=1)

from pydantic import BaseModel, ConfigDict, Field


class ResumeEvidenceOutput(BaseModel):
    """Résumé-grounded evidence for one named job-description competency."""

    model_config = ConfigDict(extra="forbid")

    competency_name: str = Field(min_length=1, max_length=255)
    evidence_found: bool
    evidence_strength: int = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str = Field(min_length=1)


class ResumeEvidenceAnalysis(BaseModel):
    """One bulk structured analysis for all competencies in a session."""

    model_config = ConfigDict(extra="forbid")

    competency_evidence: list[ResumeEvidenceOutput] = Field(default_factory=list)

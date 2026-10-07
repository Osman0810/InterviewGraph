from __future__ import annotations

import re
from collections.abc import Sequence

from app.ai.provider import AIProvider
from app.ai.prompts.resume_analysis import build_resume_analysis_prompt
from app.ai.schemas.resume_analysis import ResumeEvidenceAnalysis, ResumeEvidenceOutput


def _normalize_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
    return {"postgres": "postgresql", "postgre sql": "postgresql"}.get(normalized, normalized)


def _no_evidence(name: str) -> ResumeEvidenceOutput:
    return ResumeEvidenceOutput(
        competency_name=name,
        evidence_found=False,
        evidence_strength=0,
        evidence=[],
        confidence=0.5,
        reasoning_summary="No meaningful résumé evidence was found; this does not verify a lack of knowledge.",
    )


class ResumeEvidenceService:
    """Bulk résumé evidence analysis using the shared Gemini provider."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def analyze(self, *, resume_text: str, competencies: Sequence[object]) -> list[ResumeEvidenceOutput]:
        result = self._provider.generate_structured(
            prompt=build_resume_analysis_prompt(resume_text, competencies),
            response_schema=ResumeEvidenceAnalysis,
        )
        by_name: dict[str, ResumeEvidenceOutput] = {}
        for item in result.competency_evidence:
            by_name.setdefault(_normalize_name(item.competency_name), item)

        return [
            by_name.get(_normalize_name(competency.name), _no_evidence(competency.name))
            for competency in competencies
        ]

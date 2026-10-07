from __future__ import annotations

import re

from app.ai.provider import AIProvider
from app.ai.prompts.competency import build_competency_prompt
from app.ai.schemas.competency import CompetencyExtraction, CompetencyOutput


_NAME_ALIASES = {
    "postgres": "postgresql",
    "postgre sql": "postgresql",
}
_LEVEL_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


def _canonical_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
    return _NAME_ALIASES.get(normalized, normalized)


def normalize_competencies(items: list[CompetencyOutput]) -> list[CompetencyOutput]:
    """Merge duplicate competency names while retaining source-grounded details."""

    merged: dict[tuple[str, str], CompetencyOutput] = {}
    for item in items:
        key = (_canonical_name(item.name), item.category)
        existing = merged.get(key)
        if existing is None:
            merged[key] = item.model_copy(
                update={"name": "PostgreSQL" if key[0] == "postgresql" else item.name.strip()}
            )
            continue

        evidence = list(dict.fromkeys([existing.jd_evidence, item.jd_evidence]))
        topics = list(dict.fromkeys([*existing.question_topics, *item.question_topics]))
        required_level = (
            item.required_level
            if _LEVEL_RANK[item.required_level] > _LEVEL_RANK[existing.required_level]
            else existing.required_level
        )
        merged[key] = existing.model_copy(
            update={
                "importance": max(existing.importance, item.importance),
                "required_level": required_level,
                "jd_evidence": "\n".join(evidence),
                "question_topics": topics,
                "description": existing.description
                if len(existing.description) >= len(item.description)
                else item.description,
            }
        )

    return list(merged.values())


class JDCompetencyService:
    """Analyze a JD through the application-wide Gemini provider."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def extract_competencies(self, job_description: str) -> list[CompetencyOutput]:
        result = self._provider.generate_structured(
            prompt=build_competency_prompt(job_description),
            response_schema=CompetencyExtraction,
        )
        return normalize_competencies(result.competencies)

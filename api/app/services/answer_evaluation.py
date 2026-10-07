from __future__ import annotations

from typing import Any

from app.ai.provider import AIProvider
from app.ai.prompts.evaluation import build_evaluation_prompt
from app.ai.schemas.evaluation import AnswerEvaluationOutput


class AnswerEvaluator:
    """Uses the shared provider to evaluate one persisted interview question."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def evaluate(self, *, competency: Any, question: Any, candidate_answer: str) -> AnswerEvaluationOutput:
        return self._provider.generate_structured(
            prompt=build_evaluation_prompt(
                competency=competency,
                question=question,
                candidate_answer=candidate_answer,
            ),
            response_schema=AnswerEvaluationOutput,
        )

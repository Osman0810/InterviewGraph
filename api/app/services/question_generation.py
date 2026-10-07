from app.ai.provider import AIProvider, AIStructuredResponseError
from app.ai.prompts.questions import build_question_prompt
from app.ai.schemas.question import QuestionOutput


class QuestionGenerator:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    def generate(self, *, competency, plan, previous_questions: list[str]) -> QuestionOutput:
        result = self.provider.generate_structured(
            prompt=build_question_prompt(competency=competency, plan=plan, previous_questions=previous_questions),
            response_schema=QuestionOutput,
        )
        if (result.competency != competency.name or result.difficulty != plan.difficulty
                or result.type != plan.question_type):
            raise AIStructuredResponseError("Question does not match the application plan")
        normalized = lambda s: " ".join(s.casefold().split()).rstrip("?.!")
        if normalized(result.question) in {normalized(q) for q in previous_questions}:
            raise AIStructuredResponseError("Question repeats an earlier question")
        return result

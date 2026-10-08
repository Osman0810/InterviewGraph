import pytest
from pydantic import ValidationError

from app.ai.schemas.competency import CompetencyExtraction, CompetencyOutput
from app.ai.schemas.evaluation import AnswerEvaluationOutput
from app.ai.schemas.question import QuestionOutput
from app.ai.schemas.resume_analysis import ResumeEvidenceAnalysis
from app.ai.schemas.study_plan import StudyPlanOutput


STRUCTURED_RESPONSE_SCHEMAS = (
    CompetencyExtraction,
    ResumeEvidenceAnalysis,
    QuestionOutput,
    AnswerEvaluationOutput,
    StudyPlanOutput,
)


def _object_schemas(value: object):
    if isinstance(value, dict):
        if "properties" in value:
            yield value
        for nested in value.values():
            yield from _object_schemas(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _object_schemas(nested)


@pytest.mark.parametrize("response_schema", STRUCTURED_RESPONSE_SCHEMAS)
def test_openai_structured_response_schema_requires_all_nested_properties(response_schema) -> None:
    schema = response_schema.model_json_schema()

    for object_schema in _object_schemas(schema):
        properties = object_schema["properties"]
        assert set(object_schema.get("required", [])) == set(properties)
        assert object_schema.get("additionalProperties") is False


def test_competency_question_topics_is_required_but_accepts_an_empty_list() -> None:
    competency = CompetencyOutput(
        name="Python",
        category="Programming",
        description="Python engineering",
        importance=5,
        required_level="advanced",
        jd_evidence="Python is required.",
        question_topics=[],
    )

    assert competency.question_topics == []

    with pytest.raises(ValidationError):
        CompetencyOutput(
            name="Python",
            category="Programming",
            description="Python engineering",
            importance=5,
            required_level="advanced",
            jd_evidence="Python is required.",
        )

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import openai
import pytest

from app.ai.openai_client import OpenAIProvider
from app.ai.provider import (
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AIStructuredResponseError,
    AITimeoutError,
)
from app.ai.schemas.competency import CompetencyExtraction, CompetencyOutput


def _result() -> CompetencyExtraction:
    return CompetencyExtraction(
        competencies=[
            CompetencyOutput(
                name="Python",
                category="Programming",
                description="Python engineering",
                importance=5,
                required_level="advanced",
                jd_evidence="Python is required.",
                question_topics=["typing"],
            )
        ]
    )


def _response_with_parsed_result() -> SimpleNamespace:
    return SimpleNamespace(output_parsed=_result(), status="completed")


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def test_openai_provider_uses_responses_parse_without_network() -> None:
    client = MagicMock()
    client.responses.parse.return_value = _response_with_parsed_result()
    provider = OpenAIProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=1,
        client=client,
    )

    result = provider.generate_structured(
        prompt="Private prompt", response_schema=CompetencyExtraction
    )

    assert result == _result()
    call = client.responses.parse.call_args.kwargs
    assert call["model"] == "test-model"
    assert call["store"] is False
    assert call["text_format"] is CompetencyExtraction


@pytest.mark.parametrize("output_parsed", [None, {}])
def test_openai_provider_rejects_empty_or_invalid_structured_output_without_network(output_parsed) -> None:
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=output_parsed, status="completed")
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=1, client=client
    )

    with pytest.raises(AIStructuredResponseError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)


def test_openai_provider_maps_sdk_structured_validation_errors() -> None:
    client = MagicMock()
    client.responses.parse.side_effect = openai.APIResponseValidationError(
        httpx2.Response(200, request=_request()),
        {"private": "must not log"},
        message="invalid parsed response",
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=1, client=client
    )

    with pytest.raises(AIStructuredResponseError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)


def test_openai_provider_maps_configuration_and_authentication_without_network(caplog) -> None:
    provider = OpenAIProvider(
        api_key=None, model_name="test-model", timeout_ms=100, max_retries=1
    )
    with pytest.raises(AIConfigurationError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    client = MagicMock()
    client.responses.parse.side_effect = openai.AuthenticationError(
        "secret provider body",
        response=httpx2.Response(401, request=_request()),
        body={"secret": "must not log"},
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=1, client=client
    )
    with pytest.raises(AIConfigurationError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert "secret provider body" not in caplog.text
    assert "must not log" not in caplog.text


def test_openai_provider_maps_rate_limit_without_retries() -> None:
    client = MagicMock()
    client.responses.parse.side_effect = openai.RateLimitError(
        "rate limited",
        response=httpx2.Response(429, request=_request()),
        body={},
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=3, client=client
    )

    with pytest.raises(AIRateLimitError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert client.responses.parse.call_count == 1


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (openai.APITimeoutError(_request()), AITimeoutError),
        (
            openai.InternalServerError(
                "server error", response=httpx2.Response(503, request=_request()), body={}
            ),
            AIServiceUnavailableError,
        ),
    ],
)
def test_openai_provider_retries_timeout_and_503_with_bounded_backoff(error, expected_error) -> None:
    client = MagicMock()
    client.responses.parse.side_effect = error
    delays: list[float] = []
    provider = OpenAIProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=client,
        sleep_fn=delays.append,
        jitter_fn=lambda _minimum, _maximum: 0,
    )

    with pytest.raises(expected_error):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert client.responses.parse.call_count == 3
    assert delays == [1, 2]


def test_openai_provider_retries_connection_and_returns_a_valid_result() -> None:
    client = MagicMock()
    client.responses.parse.side_effect = [
        openai.APIConnectionError(message="connection", request=_request()),
        _response_with_parsed_result(),
    ]
    delays: list[float] = []
    provider = OpenAIProvider(
        api_key="test-key",
        model_name="test-model",
        timeout_ms=100,
        max_retries=3,
        client=client,
        sleep_fn=delays.append,
        jitter_fn=lambda _minimum, _maximum: 0,
    )

    result = provider.generate_structured(
        prompt="Private prompt", response_schema=CompetencyExtraction
    )

    assert result == _result()
    assert client.responses.parse.call_count == 2
    assert delays == [1]


def test_openai_provider_maps_non_retryable_status_errors() -> None:
    client = MagicMock()
    client.responses.parse.side_effect = openai.BadRequestError(
        "invalid request",
        response=httpx2.Response(400, request=_request()),
        body={"code": "invalid_json_schema", "param": "text.format.schema", "private": "must not log"},
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=3, client=client
    )

    with pytest.raises(AIProviderError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert client.responses.parse.call_count == 1


def test_openai_bad_request_logging_uses_safe_metadata_without_prompt_or_body(caplog) -> None:
    client = MagicMock()
    client.responses.parse.side_effect = openai.BadRequestError(
        "private provider body",
        response=httpx2.Response(400, request=_request()),
        body={"code": "invalid_json_schema", "param": "text.format.schema", "private": "must not log"},
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=1, client=client
    )

    with pytest.raises(AIProviderError):
        provider.generate_structured(prompt="Private résumé and job description", response_schema=CompetencyExtraction)

    assert "status_code': 400" in caplog.text
    assert "invalid_json_schema" in caplog.text
    assert "text.format.schema" in caplog.text
    assert "Private résumé and job description" not in caplog.text
    assert "private provider body" not in caplog.text
    assert "must not log" not in caplog.text

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


def _response_with_json() -> SimpleNamespace:
    return SimpleNamespace(output_text=_result().model_dump_json(), status="completed")


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def test_openai_provider_uses_responses_json_schema_without_network() -> None:
    client = MagicMock()
    client.responses.create.return_value = _response_with_json()
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
    call = client.responses.create.call_args.kwargs
    assert call["model"] == "test-model"
    assert call["store"] is False
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["schema"] == CompetencyExtraction.model_json_schema()
    assert call["text"]["format"]["strict"] is True


@pytest.mark.parametrize("output_text", ["", "{}"])
def test_openai_provider_rejects_empty_or_invalid_structured_output_without_network(output_text) -> None:
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(output_text=output_text, status="completed")
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
    client.responses.create.side_effect = openai.AuthenticationError(
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
    client.responses.create.side_effect = openai.RateLimitError(
        "rate limited",
        response=httpx2.Response(429, request=_request()),
        body={},
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=3, client=client
    )

    with pytest.raises(AIRateLimitError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert client.responses.create.call_count == 1


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
    client.responses.create.side_effect = error
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

    assert client.responses.create.call_count == 3
    assert delays == [1, 2]


def test_openai_provider_retries_connection_and_returns_a_valid_result() -> None:
    client = MagicMock()
    client.responses.create.side_effect = [
        openai.APIConnectionError(message="connection", request=_request()),
        _response_with_json(),
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
    assert client.responses.create.call_count == 2
    assert delays == [1]


def test_openai_provider_maps_non_retryable_status_errors() -> None:
    client = MagicMock()
    client.responses.create.side_effect = openai.BadRequestError(
        "invalid request", response=httpx2.Response(400, request=_request()), body={}
    )
    provider = OpenAIProvider(
        api_key="test-key", model_name="test-model", timeout_ms=100, max_retries=3, client=client
    )

    with pytest.raises(AIProviderError):
        provider.generate_structured(prompt="Private prompt", response_schema=CompetencyExtraction)

    assert client.responses.create.call_count == 1

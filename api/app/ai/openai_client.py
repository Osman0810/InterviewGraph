"""OpenAI implementation of the provider-neutral structured generation boundary."""

from __future__ import annotations

import logging
from random import uniform
from time import sleep
from typing import Any, Callable, TypeVar

import openai
from pydantic import BaseModel

from app.ai.provider import (
    AIConfigurationError,
    AIProvider,
    AIProviderError,
    AIRateLimitError,
    AIServiceUnavailableError,
    AIStructuredResponseError,
    AITimeoutError,
)
from app.core.config import settings


logger = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OpenAIProvider(AIProvider):
    """Shared OpenAI Responses API owner with safe structured-output handling."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        timeout_ms: int,
        max_retries: int,
        client: Any | None = None,
        sleep_fn: Callable[[float], None] = sleep,
        jitter_fn: Callable[[float, float], float] = uniform,
    ) -> None:
        self._model_name = model_name
        self._max_retries = max(1, max_retries)
        self._sleep = sleep_fn
        self._jitter = jitter_fn
        # The SDK performs one HTTP attempt; this provider owns bounded retries.
        self._client = client or (
            openai.OpenAI(
                api_key=api_key,
                timeout=timeout_ms / 1000,
                max_retries=0,
            )
            if api_key
            else None
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @classmethod
    def from_settings(cls) -> "OpenAIProvider":
        return cls(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
            timeout_ms=settings.openai_timeout_ms,
            max_retries=settings.openai_max_retries,
        )

    def generate_structured(
        self, *, prompt: str, response_schema: type[StructuredModel]
    ) -> StructuredModel:
        if self._client is None:
            raise AIConfigurationError("OpenAI is not configured on the server")

        for attempt in range(self._max_retries):
            try:
                response = self._client.responses.parse(
                    model=self._model_name,
                    input=prompt,
                    temperature=0,
                    store=False,
                    text_format=response_schema,
                )
                result = getattr(response, "output_parsed", None)
                if not isinstance(result, response_schema):
                    self._log_response_metadata(response, reason="output_parsed_missing")
                    raise AIStructuredResponseError("OpenAI returned no structured result")
                return result
            except AIStructuredResponseError:
                raise
            except openai.AuthenticationError as error:
                self._log_api_error(error)
                raise AIConfigurationError("OpenAI authentication failed") from error
            except openai.RateLimitError as error:
                self._log_api_error(error)
                raise AIRateLimitError("OpenAI rate limit exceeded") from error
            except openai.APITimeoutError as error:
                if attempt == self._max_retries - 1:
                    raise AITimeoutError("OpenAI request timed out") from error
                self._retry_with_backoff(attempt, reason="timeout")
            except openai.APIConnectionError as error:
                if attempt == self._max_retries - 1:
                    raise AIServiceUnavailableError("OpenAI service is unavailable") from error
                self._retry_with_backoff(attempt, reason="connection")
            except openai.InternalServerError as error:
                self._log_api_error(error)
                if attempt == self._max_retries - 1:
                    raise AIServiceUnavailableError("OpenAI service is unavailable") from error
                self._retry_with_backoff(attempt, reason="server_error")
            except openai.APIResponseValidationError as error:
                self._log_api_error(error)
                raise AIStructuredResponseError(
                    "OpenAI returned an invalid structured result"
                ) from error
            except openai.APIStatusError as error:
                self._log_api_error(error)
                if error.status_code >= 500:
                    if attempt == self._max_retries - 1:
                        raise AIServiceUnavailableError("OpenAI service is unavailable") from error
                    self._retry_with_backoff(attempt, reason="server_error")
                else:
                    raise AIProviderError("OpenAI request failed") from error
            except openai.APIError as error:
                self._log_api_error(error)
                raise AIProviderError("OpenAI request failed") from error

        raise AIServiceUnavailableError("OpenAI service is unavailable")

    def _retry_with_backoff(self, attempt: int, *, reason: str) -> None:
        base_delay = 2**attempt
        delay = base_delay + self._jitter(0, base_delay * 0.25)
        logger.warning("openai_retry metadata=%s", {
            "model": self._model_name,
            "operation": "responses_parse_structured",
            "attempt": attempt + 1,
            "max_attempts": self._max_retries,
            "reason": reason,
            "delay_seconds": round(delay, 3),
        })
        self._sleep(delay)

    def _log_api_error(self, error: Exception) -> None:
        logger.warning("openai_api_error metadata=%s", {
            "model": self._model_name,
            "operation": "responses_parse_structured",
            "exception_type": type(error).__name__,
            "status_code": getattr(error, "status_code", None),
            "error_code": getattr(error, "code", None),
            "parameter": getattr(error, "param", None),
        })

    def _log_response_metadata(self, response: Any, *, reason: str) -> None:
        output_parsed = getattr(response, "output_parsed", None)
        logger.warning("openai_structured_response_rejected metadata=%s", {
            "model": self._model_name,
            "operation": "responses_parse_structured",
            "reason": reason,
            "response_status": getattr(response, "status", None),
            "output_parsed_type": type(output_parsed).__name__ if output_parsed is not None else None,
        })

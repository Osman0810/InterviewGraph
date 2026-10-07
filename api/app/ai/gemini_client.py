from __future__ import annotations

from functools import lru_cache
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import logging
import json
from random import uniform
import re
from time import sleep
from typing import Any, Callable, Mapping, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

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
MAX_RATE_LIMIT_RETRY_DELAY_SECONDS = 30.0


class GeminiProvider(AIProvider):
    """The sole shared Gemini SDK owner for application services."""

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
        self._api_key = api_key
        self._model_name = model_name
        self._max_retries = max(1, max_retries)
        self._sleep = sleep_fn
        self._jitter = jitter_fn
        self._client = client or (
            genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
            if api_key
            else None
        )

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def model_name(self) -> str:
        return self._model_name

    @classmethod
    def from_settings(cls) -> "GeminiProvider":
        return cls(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
            timeout_ms=settings.gemini_timeout_ms,
            max_retries=settings.gemini_max_retries,
        )

    def generate_structured(
        self, *, prompt: str, response_schema: type[StructuredModel]
    ) -> StructuredModel:
        if self._client is None:
            raise AIConfigurationError("Gemini is not configured on the server")

        for attempt in range(self._max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_json_schema=response_schema.model_json_schema(),
                    ),
                )
                if self._is_blocked_or_empty(response):
                    self._log_response_metadata(response, reason="blocked_or_empty")
                    raise AIStructuredResponseError("Gemini did not return usable structured output")
                try:
                    output_text = response.text
                except Exception:
                    output_text = None
                if not isinstance(output_text, str) or not output_text.strip():
                    self._log_response_metadata(response, reason="output_text_missing")
                    raise AIStructuredResponseError("Gemini returned no structured result")
                try:
                    payload = json.loads(output_text)
                except json.JSONDecodeError:
                    self._log_response_metadata(response, reason="json_decode_failed")
                    raise AIStructuredResponseError("Gemini returned invalid JSON") from None
                return response_schema.model_validate(payload)
            except AIStructuredResponseError:
                raise
            except ValidationError as error:
                self._log_validation_metadata(error)
                raise AIStructuredResponseError(
                    "Gemini returned an invalid structured result"
                ) from error
            except (TimeoutError, httpx.TimeoutException) as error:
                if attempt == self._max_retries - 1:
                    raise AITimeoutError("Gemini request timed out") from error
                self._retry_with_backoff(attempt, reason="timeout")
            except httpx.TransportError as error:
                if attempt == self._max_retries - 1:
                    raise AIServiceUnavailableError("Gemini service is unavailable") from error
                self._retry_with_backoff(attempt, reason="transport")
            except errors.APIError as error:
                if getattr(error, "code", None) == 429:
                    classification, retry_delay = self._classify_rate_limit(error)
                    self._log_api_error(
                        error,
                        rate_limit_classification=classification,
                        retry_delay_seconds=retry_delay,
                    )
                    if retry_delay is None or attempt == self._max_retries - 1:
                        raise AIRateLimitError("Gemini rate limit exceeded") from error
                    self._retry_with_delay(
                        attempt,
                        delay=retry_delay,
                        reason="temporary_rate_limit",
                    )
                elif isinstance(error, errors.ServerError) or getattr(error, "code", 0) >= 500:
                    self._log_api_error(error)
                    if attempt == self._max_retries - 1:
                        raise AIServiceUnavailableError("Gemini service is unavailable") from error
                    self._retry_with_backoff(attempt, reason="server_error")
                else:
                    self._log_api_error(error)
                    raise AIProviderError("Gemini request failed") from error

        raise AIServiceUnavailableError("Gemini service is unavailable")

    def _retry_with_backoff(self, attempt: int, *, reason: str) -> None:
        """Wait once before a bounded retry, without recording sensitive request data."""
        base_delay = 2**attempt
        delay = base_delay + self._jitter(0, base_delay * 0.25)
        logger.warning("gemini_retry metadata=%s", {
            "model": self._model_name,
            "operation": "generate_content_structured",
            "attempt": attempt + 1,
            "max_attempts": self._max_retries,
            "reason": reason,
            "delay_seconds": round(delay, 3),
        })
        self._sleep(delay)

    def _retry_with_delay(self, attempt: int, *, delay: float, reason: str) -> None:
        """Honor a bounded provider retry delay without adding a rapid retry."""
        logger.warning("gemini_retry metadata=%s", {
            "model": self._model_name,
            "operation": "generate_content_structured",
            "attempt": attempt + 1,
            "max_attempts": self._max_retries,
            "reason": reason,
            "delay_seconds": round(delay, 3),
        })
        self._sleep(delay)

    def _log_api_error(
        self,
        error: errors.APIError,
        *,
        rate_limit_classification: str | None = None,
        retry_delay_seconds: float | None = None,
    ) -> None:
        """Log only provider-error metadata, never a raw provider response body."""
        metadata: dict[str, Any] = {
            "model": self._model_name,
            "operation": "generate_content_structured",
            "exception_type": type(error).__name__,
            "status_code": getattr(error, "code", None),
        }
        if rate_limit_classification is not None:
            metadata["rate_limit_classification"] = rate_limit_classification
            metadata["retry_delay_seconds"] = (
                round(retry_delay_seconds, 3) if retry_delay_seconds is not None else None
            )
        logger.warning("gemini_api_error metadata=%s", metadata)

    @classmethod
    def _classify_rate_limit(cls, error: errors.APIError) -> tuple[str, float | None]:
        """Classify 429s from safe response shape; raw provider details never leave this method."""
        text = cls._details_text(getattr(error, "details", None)).lower()
        retry_delay = cls._retry_delay_seconds(error)
        is_daily_or_project_quota = any(
            marker in text
            for marker in (
                "daily",
                "per day",
                "per_day",
                "project quota",
                "project limit",
                "quota exhausted",
                "quota exhaustion",
            )
        )
        if is_daily_or_project_quota:
            return "quota_exhausted", None
        if retry_delay is not None and retry_delay <= MAX_RATE_LIMIT_RETRY_DELAY_SECONDS:
            return "temporary_rate_limit", retry_delay
        return "rate_limit_without_safe_delay", None

    @classmethod
    def _retry_delay_seconds(cls, error: errors.APIError) -> float | None:
        header_delay = cls._retry_after_header_seconds(getattr(error, "response", None))
        if header_delay is not None:
            return header_delay
        return cls._retry_delay_from_details(getattr(error, "details", None))

    @staticmethod
    def _retry_after_header_seconds(response: Any) -> float | None:
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        value = headers.get("Retry-After") or headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, IndexError, OverflowError):
                return None

    @classmethod
    def _retry_delay_from_details(cls, details: Any) -> float | None:
        text = cls._details_text(details)
        match = re.search(r"(?:retry[_ -]?delay|retry after)\D*(\d+(?:\.\d+)?)\s*s(?:econds?)?", text, re.I)
        return float(match.group(1)) if match else None

    @classmethod
    def _details_text(cls, value: Any) -> str:
        if isinstance(value, Mapping):
            return " ".join(
                f"{key} {cls._details_text(item)}" for key, item in value.items()
            )
        if isinstance(value, (list, tuple)):
            return " ".join(cls._details_text(item) for item in value)
        return str(value) if value is not None else ""


    @staticmethod
    def _is_blocked_or_empty(response: Any) -> bool:
        """Normalize safety/empty SDK responses without exposing provider internals."""
        prompt_feedback = getattr(response, "prompt_feedback", None)
        if getattr(prompt_feedback, "block_reason", None):
            return True
        candidates = getattr(response, "candidates", None)
        if candidates is not None and not candidates:
            return True
        for candidate in candidates or []:
            finish_reason = str(getattr(candidate, "finish_reason", "")).upper()
            if "SAFETY" in finish_reason or "BLOCK" in finish_reason:
                return True
        return False

    def _log_response_metadata(self, response: Any, *, reason: str) -> None:
        """Log only shape/status metadata; never prompt or model output content."""
        candidates = getattr(response, "candidates", None) or []
        finish_reasons = [str(getattr(candidate, "finish_reason", None)) for candidate in candidates]
        try:
            output_text = response.text
        except Exception:
            output_text = None
        parsed = getattr(response, "parsed", None)
        logger.warning("gemini_structured_response_rejected metadata=%s", {
            "model": self._model_name,
            "operation": "generate_content_structured",
            "reason": reason,
            "output_text_exists": isinstance(output_text, str) and bool(output_text),
            "output_text_length": len(output_text) if isinstance(output_text, str) else 0,
            "candidate_count": len(candidates),
            "finish_reasons": finish_reasons,
            "parsed_top_level_type": type(parsed).__name__ if parsed is not None else None,
        })

    def _log_validation_metadata(self, error: ValidationError) -> None:
        logger.warning("gemini_structured_validation_failed metadata=%s", {
            "model": self._model_name,
            "operation": "generate_content_structured",
            "exception_type": type(error).__name__,
            "fields": [{"path": list(item["loc"]), "type": item["type"]} for item in error.errors()],
        })


@lru_cache
def get_gemini_provider() -> GeminiProvider:
    """Return the singleton provider used by all AI services."""

    return GeminiProvider.from_settings()


# Compatibility aliases keep existing integrations source-compatible while routes
# and services depend on the provider-neutral error hierarchy above.
GeminiProviderError = AIProviderError
GeminiConfigurationError = AIConfigurationError
GeminiTimeoutError = AITimeoutError
GeminiRateLimitError = AIRateLimitError
GeminiServiceUnavailableError = AIServiceUnavailableError
GeminiStructuredResponseError = AIStructuredResponseError

"""Provider-neutral boundary used by AI-facing services and replaceable in tests."""

from typing import Protocol, TypeVar

from pydantic import BaseModel


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Base error for safe, provider-neutral AI failures."""


class AIConfigurationError(AIProviderError):
    """Raised when the selected AI provider is not configured."""


class AITimeoutError(AIProviderError):
    """Raised after bounded provider request timeouts are exhausted."""


class AIRateLimitError(AIProviderError):
    """Raised after a provider quota or rate-limit failure."""


class AIServiceUnavailableError(AIProviderError):
    """Raised after retryable provider availability failures are exhausted."""


class AIStructuredResponseError(AIProviderError):
    """Raised when a provider response cannot satisfy the requested schema."""


class AIProvider(Protocol):
    """Common synchronous structured-generation contract for all AI providers."""

    @property
    def provider_name(self) -> str:
        """Stable provenance label persisted with AI-generated records."""

    @property
    def model_name(self) -> str:
        """The concrete model used for a generation operation."""

    def generate_structured(self, *, prompt: str, response_schema: type[StructuredModel]) -> StructuredModel: ...


# Temporary compatibility name for imports outside the application boundary.
StructuredGenerationProvider = AIProvider

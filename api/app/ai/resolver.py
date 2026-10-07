"""Centralized provider selection and session-pinned provider resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ai.gemini_client import GeminiProvider
from app.ai.openai_client import OpenAIProvider
from app.ai.provider import AIConfigurationError, AIProvider
from app.core.config import Settings, settings


ProviderName = Literal["gemini", "openai"]
SUPPORTED_PROVIDERS = frozenset({"gemini", "openai"})


class UnsupportedAIProviderError(ValueError):
    """Raised when a request names a provider outside the supported allowlist."""


@dataclass(frozen=True)
class ProviderSelection:
    provider_name: ProviderName
    model_name: str


class AIProviderResolver:
    """Owns provider-name branching; application services stay provider-neutral."""

    def __init__(self, runtime_settings: Settings = settings) -> None:
        self._settings = runtime_settings

    def select_for_new_session(self, requested_provider: str | None) -> ProviderSelection:
        provider_name = requested_provider if requested_provider is not None else self._settings.ai_provider
        return self._selection(provider_name)

    def resolve_pinned(self, provider_name: str | None, model_name: str | None) -> AIProvider:
        if provider_name is None or model_name is None:
            raise AIConfigurationError("This session has no configured AI provider")
        selection = self._selection(provider_name, pinned_model=model_name)
        if selection.provider_name == "gemini":
            return GeminiProvider(
                api_key=self._settings.gemini_api_key,
                model_name=selection.model_name,
                timeout_ms=self._settings.gemini_timeout_ms,
                max_retries=self._settings.gemini_max_retries,
            )
        return OpenAIProvider(
            api_key=self._settings.openai_api_key,
            model_name=selection.model_name,
            timeout_ms=self._settings.openai_timeout_ms,
            max_retries=self._settings.openai_max_retries,
        )

    def _selection(self, provider_name: str, *, pinned_model: str | None = None) -> ProviderSelection:
        if provider_name not in SUPPORTED_PROVIDERS:
            raise UnsupportedAIProviderError("Unsupported AI provider")
        if provider_name == "gemini":
            if not self._settings.gemini_api_key:
                raise AIConfigurationError("Gemini is not configured on the server")
            model_name = pinned_model if pinned_model is not None else self._settings.gemini_model
        else:
            if not self._settings.openai_api_key:
                raise AIConfigurationError("OpenAI is not configured on the server")
            model_name = pinned_model if pinned_model is not None else self._settings.openai_model
        if not model_name.strip():
            raise AIConfigurationError("Configured AI model is unavailable")
        return ProviderSelection(provider_name=provider_name, model_name=model_name)

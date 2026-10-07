from collections.abc import Iterable


class FakeAIProvider:
    """Deterministic test double; it never owns credentials or a network client."""

    def __init__(
        self,
        responses: Iterable[object] = (),
        error: Exception | None = None,
        *,
        provider_name: str = "test",
        model_name: str = "test-model",
    ) -> None:
        self._responses = iter(responses)
        self._error = error
        self.calls: list[dict[str, object]] = []
        self.provider_name = provider_name
        self.model_name = model_name

    def generate_structured(self, *, prompt: str, response_schema):
        self.calls.append({"prompt": prompt, "response_schema": response_schema})
        if self._error is not None:
            raise self._error
        return next(self._responses)


# Compatibility alias for the provider implementation tests.
FakeGeminiProvider = FakeAIProvider

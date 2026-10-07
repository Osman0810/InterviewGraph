from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.dependencies import get_ai_provider_resolver
from app.ai.provider import AIConfigurationError
from app.ai.resolver import AIProviderResolver, UnsupportedAIProviderError
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.interview import InterviewSession


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "gemini",
        "allow_provider_fallback": False,
        "gemini_api_key": "test-gemini-key",
        "gemini_model": "gemini-test-model",
        "openai_api_key": "test-openai-key",
        "openai_model": "openai-test-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_resolver_selects_the_configured_default_provider() -> None:
    selection = AIProviderResolver(_settings()).select_for_new_session(None)

    assert selection.provider_name == "gemini"
    assert selection.model_name == "gemini-test-model"


@pytest.mark.parametrize(
    ("requested_provider", "expected_model"),
    [("gemini", "gemini-test-model"), ("openai", "openai-test-model")],
)
def test_resolver_selects_supported_requested_provider(requested_provider, expected_model) -> None:
    selection = AIProviderResolver(_settings()).select_for_new_session(requested_provider)

    assert selection.provider_name == requested_provider
    assert selection.model_name == expected_model


def test_resolver_rejects_an_invalid_requested_provider() -> None:
    with pytest.raises(UnsupportedAIProviderError):
        AIProviderResolver(_settings()).select_for_new_session("other")


def test_resolver_requires_credentials_for_the_selected_provider() -> None:
    with pytest.raises(AIConfigurationError):
        AIProviderResolver(_settings(openai_api_key=None)).select_for_new_session("openai")


def test_resolver_never_falls_back_to_another_provider() -> None:
    resolver = AIProviderResolver(
        _settings(gemini_api_key=None, openai_api_key="available-openai-key")
    )

    with pytest.raises(AIConfigurationError):
        resolver.select_for_new_session("gemini")


def test_resolve_pinned_provider_keeps_the_original_model_after_default_changes() -> None:
    original = AIProviderResolver(_settings(gemini_model="pinned-gemini-model"))
    selection = original.select_for_new_session("gemini")
    changed_default = AIProviderResolver(_settings(gemini_model="new-gemini-default"))

    provider = changed_default.resolve_pinned(selection.provider_name, selection.model_name)

    assert provider.provider_name == "google"
    assert provider.model_name == "pinned-gemini-model"


def test_create_session_persists_selected_provider_and_server_configured_model() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    resolver = AIProviderResolver(_settings())

    def override_get_db() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ai_provider_resolver] = lambda: resolver
    try:
        response = TestClient(app).post(
            "/sessions",
            data={
                "job_description_text": "Build Python services.",
                "resume_text": "Built APIs.",
                "ai_provider": "openai",
                "ai_model": "untrusted-client-model",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    with Session(engine) as db:
        session = db.get(InterviewSession, UUID(response.json()["session_id"]))
        assert session is not None
        assert session.ai_provider == "openai"
        assert session.ai_model == "openai-test-model"
    engine.dispose()


def test_create_session_rejects_invalid_provider() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ai_provider_resolver] = lambda: AIProviderResolver(_settings())
    try:
        response = TestClient(app).post(
            "/sessions",
            data={
                "job_description_text": "Build Python services.",
                "resume_text": "Built APIs.",
                "ai_provider": "unsupported",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Unsupported AI provider"}
    engine.dispose()

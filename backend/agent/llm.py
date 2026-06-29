from __future__ import annotations

from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ValidationError

from backend.agent.types import AgentRole
from backend.config import Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when a live LLM call is requested without configuration."""


class LLMResponseError(RuntimeError):
    """Raised when a model response cannot be parsed into the expected shape."""


class LLMProviderError(RuntimeError):
    """Raised when the configured model provider rejects a request."""


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def build_chat_model(
    role: AgentRole,
    settings: Settings | None = None,
) -> BaseChatModel:
    settings = settings or get_settings()
    if not settings.openrouter_api_key:
        raise LLMConfigurationError("OPENROUTER_API_KEY is not configured")

    try:
        from langchain_openrouter import ChatOpenRouter
    except ImportError as exc:  # pragma: no cover - dependency health check.
        raise LLMConfigurationError(
            "langchain-openrouter is not installed"
        ) from exc

    kwargs: dict[str, Any] = {
        "model": _model_for(role, settings),
        "api_key": settings.openrouter_api_key,
        "base_url": settings.openrouter_base_url,
        "max_tokens": settings.openrouter_max_tokens,
        "app_url": "https://localhost/northwindai",
        "app_title": "NorthwindAI",
        "openrouter_provider": {"require_parameters": True},
    }
    if settings.openrouter_reasoning_effort:
        kwargs["reasoning"] = {"effort": settings.openrouter_reasoning_effort}
    return ChatOpenRouter(**kwargs)


def build_structured_chat_model(
    model: BaseChatModel,
    schema: type[StructuredModel],
) -> Any:
    try:
        return model.with_structured_output(
            schema,
            method="json_schema",
            strict=True,
        )
    except TypeError:
        return model.with_structured_output(schema)


def invoke_structured(chain: Any, payload: dict[str, Any]) -> StructuredModel:
    try:
        return chain.invoke(payload)
    except (LLMConfigurationError, LLMProviderError, LLMResponseError):
        raise
    except ValidationError as exc:
        raise LLMResponseError(f"structured model validation failed: {exc}") from exc
    except ValueError as exc:
        raise LLMResponseError(f"structured model response was invalid: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - provider SDKs vary by version.
        raise LLMProviderError(str(exc)) from exc


def _model_for(role: AgentRole, settings: Settings) -> str:
    return {
        AgentRole.PLANNER: settings.planner_model,
        AgentRole.SQL_WORKER: settings.sql_worker_model,
        AgentRole.CYPHER_WORKER: settings.cypher_worker_model,
        AgentRole.SYNTHESIS: settings.synthesis_model,
        AgentRole.JUDGE: settings.judge_model,
    }[role]

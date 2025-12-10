"""Application settings and model selection."""

from enum import Enum
from functools import lru_cache

from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    logfire_token: str | None = None
    max_attempts: int = 5

    # Cache settings
    cache_dir: str = ".wunderunner"
    analysis_cache_file: str = "analysis.json"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


class Analysis(Enum):
    """Analysis agent types."""

    PROJECT_STRUCTURE = "analysis.project_structure"
    BUILD_STRATEGY = "analysis.build_strategy"
    ENV_VARS = "analysis.env_vars"
    SECRETS = "analysis.secrets"
    CODE_STYLE = "analysis.code_style"


class Generation(Enum):
    """Generation agent types."""

    DOCKERFILE = "generation.dockerfile"
    COMPOSE = "generation.compose"


class Validation(Enum):
    """Validation agent types."""

    DOCKERFILE = "validation.dockerfile"
    COMPOSE = "validation.compose"


class Context(Enum):
    """Context management agent types."""

    SUMMARIZER = "context.summarizer"


AgentType = Analysis | Generation | Validation | Context


# Model priority list per agent - tried in order until one succeeds
_MODEL_PRIORITY: dict[AgentType, list[str]] = {
    # Analysis agents
    Analysis.PROJECT_STRUCTURE: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Analysis.BUILD_STRATEGY: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Analysis.ENV_VARS: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Analysis.SECRETS: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Analysis.CODE_STYLE: [
        "anthropic:claude-haiku-3-5-20241022",
        "openai:gpt-4o-mini",
    ],
    # Generation agents
    Generation.DOCKERFILE: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Generation.COMPOSE: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    # Validation agents
    Validation.DOCKERFILE: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    Validation.COMPOSE: [
        "anthropic:claude-sonnet-4-5-20250929",
        "openai:gpt-4o",
    ],
    # Context agents (use cheaper models for summarization)
    Context.SUMMARIZER: [
        "anthropic:claude-haiku-3-5-20241022",
        "openai:gpt-4o-mini",
    ],
}


class NoAPIKeyError(Exception):
    """Raised when no API keys are configured."""

    def __init__(self) -> None:
        super().__init__(
            "No API keys configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
        )


def _get_available_providers() -> set[str]:
    """Get set of available providers based on configured API keys."""
    settings = get_settings()
    providers = set()
    if settings.anthropic_api_key:
        providers.add("anthropic")
    if settings.openai_api_key:
        providers.add("openai")
    return providers


def get_model(agent: AgentType) -> Model | str:
    """Get model(s) for an agent based on priority list and available API keys.

    Args:
        agent: The agent type enum value (e.g., Analysis.CODE_STYLE)

    Returns:
        FallbackModel if multiple models available, otherwise single model string.

    Raises:
        NoAPIKeyError: If no API keys are configured
        ValueError: If agent type is unknown
    """
    if agent not in _MODEL_PRIORITY:
        raise ValueError(f"Unknown agent type: {agent}")

    available_providers = _get_available_providers()
    if not available_providers:
        raise NoAPIKeyError()

    # Filter to models we have API keys for
    priority_list = _MODEL_PRIORITY[agent]
    available_models = [
        model for model in priority_list
        if model.split(":")[0] in available_providers
    ]

    if not available_models:
        raise NoAPIKeyError()

    # Single model - return string
    if len(available_models) == 1:
        return available_models[0]

    # Multiple models - return FallbackModel
    return FallbackModel(available_models[0], *available_models[1:])

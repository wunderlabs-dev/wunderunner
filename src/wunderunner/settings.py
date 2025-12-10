"""Application settings and model selection."""

from enum import Enum
from functools import lru_cache

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
        "anthropic:claude-3-5-haiku-20241022",
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
        "anthropic:claude-3-5-haiku-20241022",
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


def get_model(agent: AgentType) -> str:
    """Get primary model string for an agent. Use get_fallback_model() at runtime for fallback.

    This returns a string to allow deferred model validation at agent creation time.
    For runtime fallback support, use get_fallback_model() which creates a FallbackModel.

    Args:
        agent: The agent type enum value (e.g., Analysis.CODE_STYLE)

    Returns:
        Model string for the first available model in priority list.

    Raises:
        NoAPIKeyError: If no API keys are configured
        ValueError: If agent type is unknown
    """
    if agent not in _MODEL_PRIORITY:
        raise ValueError(f"Unknown agent type: {agent}")

    # Return first model - agent uses defer_model_check=True so validation happens at runtime
    return _MODEL_PRIORITY[agent][0]


def _create_model(model_str: str):
    """Create a model instance with API key from settings.

    pydantic-ai providers read API keys from os.environ, but pydantic-settings
    loads .env into Settings without exporting to environ. This function
    creates model instances with explicit API keys from settings.
    """
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()
    provider, model_name = model_str.split(":", 1)

    if provider == "anthropic":
        return AnthropicModel(
            model_name,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key),
        )
    elif provider == "openai":
        return OpenAIModel(
            model_name,
            provider=OpenAIProvider(api_key=settings.openai_api_key),
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_fallback_model(agent: AgentType):
    """Get model with fallback support for runtime use.

    Creates a FallbackModel at runtime when API keys are available.
    Call this when running the agent, not at import time.

    Args:
        agent: The agent type enum value

    Returns:
        FallbackModel if multiple models available, otherwise single model instance.
    """
    from pydantic_ai.models.fallback import FallbackModel

    if agent not in _MODEL_PRIORITY:
        raise ValueError(f"Unknown agent type: {agent}")

    available_providers = _get_available_providers()
    if not available_providers:
        raise NoAPIKeyError()

    # Filter to models we have API keys for
    priority_list = _MODEL_PRIORITY[agent]
    available_models = [
        model for model in priority_list if model.split(":")[0] in available_providers
    ]

    if not available_models:
        raise NoAPIKeyError()

    # Create model instances with explicit API keys
    model_instances = [_create_model(m) for m in available_models]

    # Single model - return instance
    if len(model_instances) == 1:
        return model_instances[0]

    # Multiple models - return FallbackModel
    return FallbackModel(model_instances[0], *model_instances[1:])

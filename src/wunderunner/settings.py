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
    max_attempts: int = 3

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


AgentType = Analysis | Generation | Validation


# Model preferences per agent (best choice when both providers available)
_PREFERRED_MODELS: dict[AgentType, dict[str, str]] = {
    # Analysis agents
    Analysis.PROJECT_STRUCTURE: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Analysis.BUILD_STRATEGY: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Analysis.ENV_VARS: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Analysis.SECRETS: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Analysis.CODE_STYLE: {
        "anthropic": "anthropic:claude-haiku-3-5-20241022",
        "openai": "openai:gpt-4o-mini",
    },
    # Generation agents
    Generation.DOCKERFILE: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Generation.COMPOSE: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    # Validation agents
    Validation.DOCKERFILE: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    Validation.COMPOSE: {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
}

# Default provider preference when both are available
_DEFAULT_PROVIDER = "anthropic"


class NoAPIKeyError(Exception):
    """Raised when no API keys are configured."""

    def __init__(self) -> None:
        super().__init__(
            "No API keys configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
        )


def get_available_provider() -> str:
    """Get the available provider based on configured API keys.

    Returns the preferred provider if both are available.
    Raises NoAPIKeyError if neither is configured.
    """
    settings = get_settings()

    has_anthropic = bool(settings.anthropic_api_key)
    has_openai = bool(settings.openai_api_key)

    if has_anthropic and has_openai:
        return _DEFAULT_PROVIDER
    if has_anthropic:
        return "anthropic"
    if has_openai:
        return "openai"

    raise NoAPIKeyError()


def get_model(agent: AgentType) -> str:
    """Get the best available model for a given agent.

    Args:
        agent: The agent type enum value (e.g., Analysis.CODE_STYLE)

    Returns:
        Model string in pydantic-ai format (e.g., "anthropic:claude-sonnet-4-5-20250929")

    Raises:
        NoAPIKeyError: If no API keys are configured
        ValueError: If agent type is unknown
    """
    if agent not in _PREFERRED_MODELS:
        raise ValueError(f"Unknown agent type: {agent}")

    provider = get_available_provider()
    return _PREFERRED_MODELS[agent][provider]

"""Application settings and model selection."""

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Model preferences per task (best choice when both providers available)
_PREFERRED_MODELS: dict[str, dict[str, str]] = {
    "analysis": {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    "dockerfile": {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    "compose": {
        "anthropic": "anthropic:claude-sonnet-4-5-20250929",
        "openai": "openai:gpt-4o",
    },
    "validation": {
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


def get_model(task: str) -> str:
    """Get the best available model for a given task.

    Args:
        task: The task type (analysis, dockerfile, compose, validation)

    Returns:
        Model string in pydantic-ai format (e.g., "anthropic:claude-sonnet-4-5-20250929")

    Raises:
        NoAPIKeyError: If no API keys are configured
        ValueError: If task is unknown
    """
    if task not in _PREFERRED_MODELS:
        raise ValueError(f"Unknown task: {task}. Valid tasks: {list(_PREFERRED_MODELS.keys())}")

    provider = get_available_provider()
    return _PREFERRED_MODELS[task][provider]

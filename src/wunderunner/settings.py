"""Application settings and model selection."""

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from wunderunner.auth.client import get_anthropic_client
from wunderunner.auth.models import Provider
from wunderunner.exceptions import NoAuthError


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


# Model tiers - most agents use standard, some use fast for cheaper tasks
_STANDARD_MODELS = ["anthropic:claude-sonnet-4-5-20250929", "openai:gpt-4o"]
_FAST_MODELS = ["anthropic:claude-3-5-haiku-20241022", "openai:gpt-4o-mini"]

# Agents that use fast (cheaper) models
_FAST_AGENTS: set[AgentType] = {Analysis.CODE_STYLE, Context.SUMMARIZER}


def _get_model_priority(agent: AgentType) -> list[str]:
    """Get model priority list for an agent."""
    return _FAST_MODELS if agent in _FAST_AGENTS else _STANDARD_MODELS


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
    """
    # Return first model - agent uses defer_model_check=True so validation happens at runtime
    return _get_model_priority(agent)[0]


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

    available_providers = _get_available_providers()
    if not available_providers:
        raise NoAPIKeyError()

    # Filter to models we have API keys for
    priority_list = _get_model_priority(agent)
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


async def create_model_async(model_str: str):
    """Create a model instance with OAuth or API key authentication.

    Priority: OAuth tokens → API key → NoAuthError

    Args:
        model_str: Model string in format "provider:model_name"

    Returns:
        Configured model instance.

    Raises:
        NoAuthError: If no authentication is configured for the provider.
    """
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()
    provider, model_name = model_str.split(":", 1)

    if provider == Provider.ANTHROPIC.value:
        # Try OAuth first
        oauth_client = await get_anthropic_client()
        if oauth_client:
            # OAuth client already has Bearer token, pass dummy API key
            return AnthropicModel(
                model_name,
                provider=AnthropicProvider(
                    api_key="oauth-placeholder",
                    http_client=oauth_client
                ),
            )
        # Fall back to API key
        if settings.anthropic_api_key:
            return AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=settings.anthropic_api_key),
            )
        raise NoAuthError(Provider.ANTHROPIC.value)

    elif provider == Provider.OPENAI.value:
        # OpenAI: API key only
        if settings.openai_api_key:
            return OpenAIModel(
                model_name,
                provider=OpenAIProvider(api_key=settings.openai_api_key),
            )
        raise NoAuthError(Provider.OPENAI.value)

    else:
        raise ValueError(f"Unknown provider: {provider}")

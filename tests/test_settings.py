"""Tests for settings module."""

from unittest.mock import MagicMock, patch

import pytest

from wunderunner.settings import (
    Analysis,
    Context,
    Generation,
    NoAPIKeyError,
    Settings,
    Validation,
    _create_model,
    _get_available_providers,
    _get_model_priority,
    get_fallback_model,
    get_model,
    get_settings,
)


class TestSettings:
    """Test Settings class configuration."""

    def test_settings_defaults(self):
        """Settings has correct default values."""
        with patch.dict("os.environ", {}, clear=True):
            # Clear lru_cache to get fresh settings
            get_settings.cache_clear()
            # Disable .env file loading for this test
            with patch.object(Settings, "model_config", {"env_file": None}):
                settings = Settings()
                assert settings.anthropic_api_key is None
                assert settings.openai_api_key is None
                assert settings.logfire_token is None
                assert settings.max_attempts == 5
                assert settings.cache_dir == ".wunderunner"
                assert settings.analysis_cache_file == "analysis.json"

    def test_settings_loads_from_env(self):
        """Settings loads API keys from environment."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-ant-test123",
                "OPENAI_API_KEY": "sk-openai-test456",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = Settings()
            assert settings.anthropic_api_key == "sk-ant-test123"
            assert settings.openai_api_key == "sk-openai-test456"


class TestGetSettings:
    """Test get_settings caching."""

    def test_get_settings_returns_same_instance(self):
        """get_settings returns cached instance."""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_creates_new_instance(self):
        """Clearing cache creates new Settings."""
        get_settings.cache_clear()
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        # Different instances but equal values
        assert s1 is not s2


class TestAgentTypes:
    """Test agent type enums."""

    def test_analysis_agents(self):
        """Analysis enum has expected values."""
        assert Analysis.PROJECT_STRUCTURE.value == "analysis.project_structure"
        assert Analysis.BUILD_STRATEGY.value == "analysis.build_strategy"
        assert Analysis.ENV_VARS.value == "analysis.env_vars"
        assert Analysis.SECRETS.value == "analysis.secrets"
        assert Analysis.CODE_STYLE.value == "analysis.code_style"

    def test_generation_agents(self):
        """Generation enum has expected values."""
        assert Generation.DOCKERFILE.value == "generation.dockerfile"
        assert Generation.COMPOSE.value == "generation.compose"

    def test_validation_agents(self):
        """Validation enum has expected values."""
        assert Validation.DOCKERFILE.value == "validation.dockerfile"
        assert Validation.COMPOSE.value == "validation.compose"

    def test_context_agents(self):
        """Context enum has expected values."""
        assert Context.SUMMARIZER.value == "context.summarizer"


class TestModelPriority:
    """Test model priority selection."""

    def test_fast_agents_get_fast_models(self):
        """Fast agents (CODE_STYLE, SUMMARIZER) get fast model list."""
        priority = _get_model_priority(Analysis.CODE_STYLE)
        assert "haiku" in priority[0]

        priority = _get_model_priority(Context.SUMMARIZER)
        assert "haiku" in priority[0]

    def test_standard_agents_get_standard_models(self):
        """Standard agents get standard model list."""
        priority = _get_model_priority(Generation.DOCKERFILE)
        assert "sonnet" in priority[0]

        priority = _get_model_priority(Analysis.PROJECT_STRUCTURE)
        assert "sonnet" in priority[0]


class TestGetAvailableProviders:
    """Test provider detection from API keys."""

    def test_no_keys_returns_empty_set(self):
        """No API keys means no providers."""
        with patch("wunderunner.settings.get_settings") as mock:
            mock_settings = MagicMock()
            mock_settings.anthropic_api_key = None
            mock_settings.openai_api_key = None
            mock.return_value = mock_settings
            providers = _get_available_providers()
            assert providers == set()

    def test_anthropic_key_only(self):
        """Only Anthropic key returns anthropic provider."""
        with patch("wunderunner.settings.get_settings") as mock:
            mock_settings = MagicMock()
            mock_settings.anthropic_api_key = "sk-ant-test"
            mock_settings.openai_api_key = None
            mock.return_value = mock_settings
            providers = _get_available_providers()
            assert providers == {"anthropic"}

    def test_openai_key_only(self):
        """Only OpenAI key returns openai provider."""
        with patch("wunderunner.settings.get_settings") as mock:
            mock_settings = MagicMock()
            mock_settings.anthropic_api_key = None
            mock_settings.openai_api_key = "sk-openai-test"
            mock.return_value = mock_settings
            providers = _get_available_providers()
            assert providers == {"openai"}

    def test_both_keys_returns_both_providers(self):
        """Both keys returns both providers."""
        with patch("wunderunner.settings.get_settings") as mock:
            mock_settings = MagicMock()
            mock_settings.anthropic_api_key = "sk-ant-test"
            mock_settings.openai_api_key = "sk-openai-test"
            mock.return_value = mock_settings
            providers = _get_available_providers()
            assert providers == {"anthropic", "openai"}


class TestNoAPIKeyError:
    """Test NoAPIKeyError exception."""

    def test_error_message(self):
        """NoAPIKeyError has helpful message."""
        error = NoAPIKeyError()
        assert "ANTHROPIC_API_KEY" in str(error)
        assert "OPENAI_API_KEY" in str(error)


class TestGetModel:
    """Test get_model function."""

    def test_returns_first_model_in_priority(self):
        """get_model returns first model string."""
        model = get_model(Generation.DOCKERFILE)
        assert "anthropic:" in model or "openai:" in model

    def test_fast_agent_gets_fast_model(self):
        """Fast agent gets haiku or mini model."""
        model = get_model(Analysis.CODE_STYLE)
        assert "haiku" in model or "mini" in model


class TestCreateModel:
    """Test _create_model function."""

    def test_creates_anthropic_model(self):
        """_create_model creates AnthropicModel for anthropic: prefix."""
        from pydantic_ai.models.anthropic import AnthropicModel

        with patch("wunderunner.settings.get_settings") as mock_settings:
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"

            result = _create_model("anthropic:claude-3-5-sonnet-20241022")

            # Verify it's a real AnthropicModel instance
            assert isinstance(result, AnthropicModel)
            # Verify it has the correct model name
            assert result.model_name == "claude-3-5-sonnet-20241022"

    def test_creates_openai_model(self):
        """_create_model creates OpenAIModel for openai: prefix."""
        from pydantic_ai.models.openai import OpenAIModel

        with patch("wunderunner.settings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "sk-openai-test"

            result = _create_model("openai:gpt-4o")

            # Verify it's a real OpenAIModel instance
            assert isinstance(result, OpenAIModel)
            # Verify it has the correct model name
            assert result.model_name == "gpt-4o"

    def test_unknown_provider_raises(self):
        """_create_model raises for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            _create_model("unknown:model-name")


class TestGetFallbackModel:
    """Test get_fallback_model function."""

    def test_no_api_keys_raises_error(self):
        """get_fallback_model raises NoAPIKeyError when no keys configured."""
        with patch("wunderunner.settings._get_available_providers", return_value=set()):
            with pytest.raises(NoAPIKeyError):
                get_fallback_model(Generation.DOCKERFILE)

    def test_single_provider_returns_single_model(self):
        """Single provider returns model instance (not FallbackModel)."""
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.models.fallback import FallbackModel

        with patch("wunderunner.settings.get_settings") as mock_settings:
            # Only anthropic key available
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"
            mock_settings.return_value.openai_api_key = None

            result = get_fallback_model(Generation.DOCKERFILE)

            # Should return a real AnthropicModel, not a FallbackModel
            assert isinstance(result, AnthropicModel)
            assert not isinstance(result, FallbackModel)

    def test_multiple_providers_returns_fallback_model(self):
        """Multiple providers returns FallbackModel."""
        from pydantic_ai.models.fallback import FallbackModel

        with patch("wunderunner.settings.get_settings") as mock_settings:
            # Both keys available
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"
            mock_settings.return_value.openai_api_key = "sk-openai-test"

            result = get_fallback_model(Generation.DOCKERFILE)

            # Should return a real FallbackModel instance
            assert isinstance(result, FallbackModel)


class TestCreateModelWithOAuth:
    """Test create_model_async with OAuth integration."""

    @pytest.mark.asyncio
    async def test_uses_oauth_client_when_available(self):
        """create_model_async uses OAuth client when tokens exist."""
        import time
        from unittest.mock import AsyncMock
        import httpx

        # Create a mock OAuth client
        mock_client = httpx.AsyncClient(
            headers={
                "Authorization": "Bearer oauth_token",
                "anthropic-beta": "oauth-2025-04-20",
            }
        )

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = mock_client
            mock_settings.return_value.anthropic_api_key = None

            from wunderunner.settings import create_model_async
            model = await create_model_async("anthropic:claude-3-5-sonnet-20241022")

            mock_get_client.assert_called_once()
            # Model should be created (we can't easily verify the client was used)
            assert model is not None

    @pytest.mark.asyncio
    async def test_falls_back_to_api_key(self):
        """create_model_async falls back to API key when no OAuth."""
        from unittest.mock import AsyncMock

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = None  # No OAuth
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"

            from wunderunner.settings import create_model_async
            model = await create_model_async("anthropic:claude-3-5-sonnet-20241022")

            assert model is not None

    @pytest.mark.asyncio
    async def test_raises_no_auth_error(self):
        """create_model_async raises NoAuthError when no auth configured."""
        from unittest.mock import AsyncMock
        from wunderunner.exceptions import NoAuthError

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = None
            mock_settings.return_value.anthropic_api_key = None

            from wunderunner.settings import create_model_async

            with pytest.raises(NoAuthError):
                await create_model_async("anthropic:claude-3-5-sonnet-20241022")

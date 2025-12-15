"""Tests for services detection agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jinja2 import Template

from wunderunner.agents.analysis.services import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.models.analysis import DetectedService


class TestServicesPrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined and non-empty."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100

    def test_user_prompt_is_template(self):
        """User prompt is a Jinja2 template."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, Template)

    def test_system_prompt_mentions_services(self):
        """System prompt explains service detection."""
        assert "service" in SYSTEM_PROMPT.lower()

    def test_system_prompt_lists_supported_services(self):
        """System prompt lists supported service types."""
        assert "postgres" in SYSTEM_PROMPT.lower()
        assert "redis" in SYSTEM_PROMPT.lower()
        assert "mysql" in SYSTEM_PROMPT.lower()
        assert "mongodb" in SYSTEM_PROMPT.lower()

    def test_system_prompt_has_confidence_scoring(self):
        """System prompt explains confidence scoring."""
        assert "confidence" in SYSTEM_PROMPT.lower()
        assert "1.0" in SYSTEM_PROMPT or "0.8" in SYSTEM_PROMPT


class TestServicesAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return list of DetectedService."""
        assert agent._output_type == list[DetectedService]

    def test_agent_has_no_deps_type(self):
        """Services agent doesn't need file access."""
        assert agent._deps_type is None or agent._deps_type == type(None)

    def test_agent_has_no_tools(self):
        """Services agent analyzes env vars text only."""
        tools = agent._function_toolset.tools
        assert len(tools) == 0


class TestDetectedServiceModel:
    """Test DetectedService model."""

    def test_detected_service_fields(self):
        """DetectedService has required fields."""
        service = DetectedService(
            type="postgres",
            env_vars=["DATABASE_URL", "DATABASE_HOST"],
            confidence=0.9,
        )
        assert service.type == "postgres"
        assert "DATABASE_URL" in service.env_vars
        assert service.confidence == 0.9

    def test_confidence_range(self):
        """Confidence is 0-1 float."""
        service = DetectedService(
            type="redis",
            env_vars=["REDIS_URL"],
            confidence=0.8,
        )
        assert 0 <= service.confidence <= 1

    def test_env_vars_list(self):
        """env_vars is a list of strings."""
        service = DetectedService(
            type="mongodb",
            env_vars=["MONGO_URL", "MONGO_HOST", "MONGO_PORT"],
            confidence=0.95,
        )
        assert len(service.env_vars) == 3


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_env_vars(self):
        """Template renders environment variables."""
        env_vars = [
            MagicMock(name="DATABASE_URL", secret=False, service=None),
            MagicMock(name="PORT", secret=False, service=None),
        ]
        # Fix mock .name attribute
        env_vars[0].name = "DATABASE_URL"
        env_vars[0].secret = False
        env_vars[0].service = None
        env_vars[1].name = "PORT"
        env_vars[1].secret = False
        env_vars[1].service = None

        rendered = USER_PROMPT.render(env_vars=env_vars)
        assert "DATABASE_URL" in rendered
        assert "PORT" in rendered

    def test_renders_secrets_marked(self):
        """Template marks secrets in output."""
        env_vars = [
            MagicMock(name="API_KEY", secret=True, service=None),
        ]
        env_vars[0].name = "API_KEY"
        env_vars[0].secret = True
        env_vars[0].service = None

        rendered = USER_PROMPT.render(env_vars=env_vars)
        assert "API_KEY" in rendered
        assert "secret" in rendered

    def test_renders_service_hints(self):
        """Template shows existing service hints."""
        env_vars = [
            MagicMock(name="DATABASE_URL", secret=False, service="postgres"),
        ]
        env_vars[0].name = "DATABASE_URL"
        env_vars[0].secret = False
        env_vars[0].service = "postgres"

        rendered = USER_PROMPT.render(env_vars=env_vars)
        assert "postgres" in rendered


class TestServicesAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_detected_services(self):
        """Agent returns list of DetectedService."""
        mock_result = [
            DetectedService(
                type="postgres",
                env_vars=["DATABASE_URL", "DATABASE_HOST"],
                confidence=0.9,
            ),
            DetectedService(
                type="redis",
                env_vars=["REDIS_URL"],
                confidence=1.0,
            ),
        ]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert len(result.output) == 2
            assert result.output[0].type == "postgres"
            assert result.output[1].type == "redis"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_services(self):
        """Agent returns empty list when no services detected."""
        mock_result = []
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert result.output == []

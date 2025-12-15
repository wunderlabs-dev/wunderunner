"""Tests for docker-compose generation agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jinja2 import Template

from wunderunner.agents.generation.compose import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    ComposeResult,
    agent,
)


class TestComposePrompts:
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

    def test_system_prompt_mentions_compose(self):
        """System prompt mentions docker-compose."""
        assert "compose" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_no_volumes(self):
        """System prompt explicitly forbids volumes."""
        assert "volume" in SYSTEM_PROMPT.lower()
        assert "never" in SYSTEM_PROMPT.lower() or "no volume" in SYSTEM_PROMPT.lower()

    def test_system_prompt_has_service_templates(self):
        """System prompt includes service container templates."""
        assert "postgres:" in SYSTEM_PROMPT
        assert "redis:" in SYSTEM_PROMPT
        assert "mysql:" in SYSTEM_PROMPT
        assert "mongodb:" in SYSTEM_PROMPT

    def test_system_prompt_mentions_depends_on(self):
        """System prompt explains depends_on for ordering."""
        assert "depends_on" in SYSTEM_PROMPT


class TestComposeAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return ComposeResult."""
        assert agent._output_type == ComposeResult

    def test_agent_has_no_deps_type(self):
        """Compose agent doesn't need file access."""
        assert agent._deps_type is None or agent._deps_type == type(None)

    def test_agent_has_no_tools(self):
        """Compose agent has no filesystem tools."""
        # This agent gets all info from the prompt (Dockerfile, analysis, errors)
        tools = agent._function_toolset.tools
        assert len(tools) == 0


class TestComposeResult:
    """Test ComposeResult model."""

    def test_compose_result_fields(self):
        """ComposeResult has compose_yaml field."""
        result = ComposeResult(
            compose_yaml="services:\n  app:\n    build: ."
        )
        assert "services:" in result.compose_yaml

    def test_compose_result_accepts_multiline(self):
        """ComposeResult accepts multiline YAML."""
        yaml_content = """services:
  app:
    build: .
    ports:
      - "3000:3000"
  postgres:
    image: postgres:16-alpine
"""
        result = ComposeResult(compose_yaml=yaml_content)
        assert "postgres:" in result.compose_yaml


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_project_info(self):
        """Template renders project info from analysis."""
        analysis = MagicMock()
        analysis.project_structure.runtime = "node"
        analysis.project_structure.framework = "express"
        analysis.project_structure.port = 3000

        rendered = USER_PROMPT.render(
            analysis=analysis,
            dockerfile="FROM node:20",
            services=None,
            learnings=None,
            existing_compose=None,
        )
        assert "node" in rendered
        assert "3000" in rendered

    def test_renders_dockerfile(self):
        """Template includes dockerfile content."""
        analysis = MagicMock()
        analysis.project_structure.runtime = "node"
        analysis.project_structure.framework = None
        analysis.project_structure.port = 3000

        rendered = USER_PROMPT.render(
            analysis=analysis,
            dockerfile="FROM node:20\nWORKDIR /app\nCMD npm start",
            services=None,
            learnings=None,
            existing_compose=None,
        )
        assert "FROM node:20" in rendered
        assert "WORKDIR /app" in rendered

    def test_renders_services(self):
        """Template renders services to create."""
        analysis = MagicMock()
        analysis.project_structure.runtime = "node"
        analysis.project_structure.framework = None
        analysis.project_structure.port = 3000

        services = [
            {"type": "postgres", "env_vars": ["DATABASE_URL", "DATABASE_HOST"]},
            {"type": "redis", "env_vars": ["REDIS_URL"]},
        ]

        rendered = USER_PROMPT.render(
            analysis=analysis,
            dockerfile="FROM node:20",
            services=services,
            learnings=None,
            existing_compose=None,
        )
        assert "postgres" in rendered
        assert "redis" in rendered
        assert "DATABASE_URL" in rendered

    def test_renders_learnings(self):
        """Template renders previous errors."""
        analysis = MagicMock()
        analysis.project_structure.runtime = "node"
        analysis.project_structure.framework = None
        analysis.project_structure.port = 3000

        learnings = [
            MagicMock(phase="START", error_message="Port 3000 already in use"),
        ]

        rendered = USER_PROMPT.render(
            analysis=analysis,
            dockerfile="FROM node:20",
            services=None,
            learnings=learnings,
            existing_compose=None,
        )
        assert "START" in rendered
        assert "Port 3000" in rendered

    def test_renders_existing_compose_for_fixes(self):
        """Template renders existing compose for fixes."""
        analysis = MagicMock()
        analysis.project_structure.runtime = "node"
        analysis.project_structure.framework = None
        analysis.project_structure.port = 3000

        rendered = USER_PROMPT.render(
            analysis=analysis,
            dockerfile="FROM node:20",
            services=None,
            learnings=None,
            existing_compose="services:\n  app:\n    build: .",
        )
        assert "services:" in rendered
        assert "Fix the errors" in rendered


class TestComposeAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_compose_yaml(self):
        """Agent returns ComposeResult with valid YAML."""
        mock_result = ComposeResult(
            compose_yaml="services:\n  app:\n    build: .\n    ports:\n      - '3000:3000'"
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert "services:" in result.output.compose_yaml
            assert "build: ." in result.output.compose_yaml

    @pytest.mark.asyncio
    async def test_returns_compose_with_services(self):
        """Agent returns compose with service containers."""
        mock_result = ComposeResult(
            compose_yaml="""services:
  app:
    build: .
    ports:
      - "3000:3000"
    depends_on:
      - postgres
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
"""
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert "postgres:" in result.output.compose_yaml
            assert "depends_on:" in result.output.compose_yaml

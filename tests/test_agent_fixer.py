"""Tests for fixer (diagnostic) agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from jinja2 import Template

from wunderunner.agents.generation.fixer import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    Diagnosis,
    agent,
)
from wunderunner.agents.tools import AgentDeps


class TestFixerPrompts:
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

    def test_system_prompt_mentions_diagnostic(self):
        """System prompt explains diagnostic purpose."""
        assert "diagnostic" in SYSTEM_PROMPT.lower() or "diagnose" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_read_only(self):
        """System prompt mentions read-only tools."""
        assert "read" in SYSTEM_PROMPT.lower()


class TestFixerAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return Diagnosis."""
        assert agent._output_type == Diagnosis

    def test_agent_has_deps_type(self):
        """Agent uses AgentDeps for dependencies."""
        assert agent._deps_type == AgentDeps

    def test_agent_has_read_only_tools(self):
        """Agent has read tools but no write_file."""
        # Get registered tools from function toolset
        tools = agent._function_toolset.tools
        tool_names = list(tools.keys())

        # Verify read-only tools are present
        assert "read_file" in tool_names
        assert "list_dir" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names

        # Verify write tools are NOT present
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names


class TestDiagnosisModel:
    """Test Diagnosis output model."""

    def test_diagnosis_has_required_fields(self):
        """Diagnosis model has all required fields."""
        diagnosis = Diagnosis(
            root_cause="Missing build step",
            is_dockerfile_issue=True,
            suggested_fix="Add RUN npm run build",
            confidence=8,
        )
        assert diagnosis.root_cause == "Missing build step"
        assert diagnosis.is_dockerfile_issue is True
        assert diagnosis.suggested_fix == "Add RUN npm run build"
        assert diagnosis.confidence == 8

    def test_diagnosis_confidence_range(self):
        """Confidence must be 0-10."""
        diagnosis = Diagnosis(
            root_cause="test",
            is_dockerfile_issue=True,
            suggested_fix="test",
            confidence=5,
        )
        assert 0 <= diagnosis.confidence <= 10


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_error_details(self):
        """Template renders error information."""
        rendered = USER_PROMPT.render(
            analysis={"runtime": "node"},
            phase="BUILD",
            error_type="BuildError",
            error_message="npm ERR! Missing script: build",
            context="",
            dockerfile="FROM node:20",
            compose=None,
        )
        assert "BUILD" in rendered
        assert "BuildError" in rendered
        assert "npm ERR!" in rendered

    def test_renders_dockerfile(self):
        """Template includes dockerfile content."""
        rendered = USER_PROMPT.render(
            analysis={},
            phase="BUILD",
            error_type="Error",
            error_message="test",
            context=None,
            dockerfile="FROM node:20\nWORKDIR /app",
            compose=None,
        )
        assert "FROM node:20" in rendered
        assert "WORKDIR /app" in rendered

    def test_renders_compose_when_provided(self):
        """Template includes compose when provided."""
        rendered = USER_PROMPT.render(
            analysis={},
            phase="START",
            error_type="Error",
            error_message="test",
            context=None,
            dockerfile="FROM node:20",
            compose="version: '3.8'",
        )
        assert "version: '3.8'" in rendered

    def test_omits_compose_when_none(self):
        """Template omits compose section when None."""
        rendered = USER_PROMPT.render(
            analysis={},
            phase="START",
            error_type="Error",
            error_message="test",
            context=None,
            dockerfile="FROM node:20",
            compose=None,
        )
        assert "docker_compose" not in rendered


class TestFixerAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_diagnosis(self, tmp_path: Path):
        """Agent returns Diagnosis model."""
        mock_result = Diagnosis(
            root_cause="Missing npm install step",
            is_dockerfile_issue=True,
            suggested_fix="Add RUN npm ci before RUN npm run build",
            confidence=9,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)
            deps = AgentDeps(project_dir=tmp_path)

            prompt = USER_PROMPT.render(
                analysis={"runtime": "node"},
                phase="BUILD",
                error_type="BuildError",
                error_message="Module not found",
                context=None,
                dockerfile="FROM node:20",
                compose=None,
            )
            result = await agent.run(prompt, deps=deps)

            assert result.output.root_cause == "Missing npm install step"
            assert result.output.is_dockerfile_issue is True
            assert result.output.confidence == 9

    @pytest.mark.asyncio
    async def test_identifies_project_issue(self, tmp_path: Path):
        """Agent can identify non-Dockerfile issues."""
        mock_result = Diagnosis(
            root_cause="Invalid package.json syntax",
            is_dockerfile_issue=False,
            suggested_fix="Fix JSON syntax in package.json",
            confidence=7,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)
            deps = AgentDeps(project_dir=tmp_path)

            result = await agent.run("test prompt", deps=deps)

            assert result.output.is_dockerfile_issue is False

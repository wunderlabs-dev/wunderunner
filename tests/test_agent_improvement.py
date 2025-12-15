"""Tests for improvement agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from jinja2 import Template

from wunderunner.agents.generation.improvement import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.generation import ImprovementResult


class TestImprovementPrompts:
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

    def test_system_prompt_mentions_devops(self):
        """System prompt establishes DevOps persona."""
        assert "devops" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_development(self):
        """System prompt clarifies development containers."""
        assert "development" in SYSTEM_PROMPT.lower() or "dev" in SYSTEM_PROMPT.lower()


class TestImprovementAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return ImprovementResult."""
        assert agent._output_type == ImprovementResult

    def test_agent_has_deps_type(self):
        """Agent uses AgentDeps for dependencies."""
        assert agent._deps_type == AgentDeps

    def test_agent_has_write_tools(self):
        """Agent has write_file tool (opposite of fixer)."""
        # Get registered tools from function toolset
        tools = agent._function_toolset.tools
        tool_names = list(tools.keys())

        # Verify read tools are present
        assert "read_file" in tool_names
        assert "list_dir" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names

        # Verify write tools ARE present (opposite of fixer)
        assert "write_file" in tool_names
        assert "edit_file" in tool_names


class TestImprovementResult:
    """Test ImprovementResult model."""

    def test_improvement_result_fields(self):
        """ImprovementResult has all required fields."""
        result = ImprovementResult(
            dockerfile="FROM node:20\nCMD npm run dev",
            confidence=8,
            reasoning="Changed to dev mode",
            files_modified=[],
        )
        assert "FROM node:20" in result.dockerfile
        assert result.confidence == 8
        assert result.reasoning == "Changed to dev mode"
        assert result.files_modified == []

    def test_strips_markdown_fences(self):
        """Dockerfile content has markdown fences stripped."""
        result = ImprovementResult(
            dockerfile="```dockerfile\nFROM node:20\n```",
            confidence=5,
            reasoning="test",
        )
        assert result.dockerfile == "FROM node:20"
        assert "```" not in result.dockerfile

    def test_files_modified_default_empty(self):
        """files_modified defaults to empty list."""
        result = ImprovementResult(
            dockerfile="FROM node:20",
            confidence=5,
            reasoning="test",
        )
        assert result.files_modified == []


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_build_failure(self):
        """Template renders build failure details."""
        rendered = USER_PROMPT.render(
            attempt_number=2,
            dockerfile="FROM node:20",
            phase="BUILD",
            exit_code=1,
            error_message="npm ERR! Missing script: build",
            historical_fixes=None,
        )
        assert "2" in rendered  # attempt number
        assert "BUILD" in rendered
        assert "npm ERR!" in rendered

    def test_renders_previous_dockerfile(self):
        """Template includes previous dockerfile."""
        rendered = USER_PROMPT.render(
            attempt_number=1,
            dockerfile="FROM node:20\nWORKDIR /app\nCOPY . .",
            phase="BUILD",
            exit_code=1,
            error_message="error",
            historical_fixes=None,
        )
        assert "FROM node:20" in rendered
        assert "WORKDIR /app" in rendered

    def test_renders_historical_fixes(self):
        """Template includes historical fixes when provided."""
        fixes = [
            {"fix": "Added ARG DATABASE_URL", "explanation": "For build-time secrets"},
            {"fix": "Changed to node:20", "explanation": "For native deps"},
        ]
        rendered = USER_PROMPT.render(
            attempt_number=3,
            dockerfile="FROM node:20",
            phase="BUILD",
            exit_code=1,
            error_message="error",
            historical_fixes=fixes,
        )
        assert "ARG DATABASE_URL" in rendered
        assert "build-time secrets" in rendered
        assert "native deps" in rendered

    def test_omits_historical_fixes_when_none(self):
        """Template omits history section when no fixes."""
        rendered = USER_PROMPT.render(
            attempt_number=1,
            dockerfile="FROM node:20",
            phase="BUILD",
            exit_code=1,
            error_message="error",
            historical_fixes=None,
        )
        assert "historical_learnings" not in rendered


class TestImprovementAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_improved_dockerfile(self, tmp_path: Path):
        """Agent returns improved dockerfile."""
        mock_result = ImprovementResult(
            dockerfile="FROM node:20\nWORKDIR /app\nCOPY . .\nCMD npm run dev",
            confidence=9,
            reasoning="Changed to dev mode for development container",
            files_modified=[],
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)
            deps = AgentDeps(project_dir=tmp_path)

            result = await agent.run("test prompt", deps=deps)

            assert "npm run dev" in result.output.dockerfile
            assert result.output.confidence == 9

    @pytest.mark.asyncio
    async def test_returns_files_modified(self, tmp_path: Path):
        """Agent reports modified files."""
        mock_result = ImprovementResult(
            dockerfile="FROM node:20",
            confidence=7,
            reasoning="Removed conflicting .babelrc",
            files_modified=[".babelrc"],
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)
            deps = AgentDeps(project_dir=tmp_path)

            result = await agent.run("test prompt", deps=deps)

            assert ".babelrc" in result.output.files_modified

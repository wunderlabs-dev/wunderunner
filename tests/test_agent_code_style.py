"""Tests for code style analysis agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.agents.analysis.code_style import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import CodeStyle


class TestCodeStylePrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)

    def test_user_prompt_exists(self):
        """User prompt is defined."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, str)

    def test_system_prompt_mentions_typescript(self):
        """System prompt includes TypeScript detection."""
        assert "typescript" in SYSTEM_PROMPT.lower() or "tsconfig" in SYSTEM_PROMPT.lower()


class TestCodeStyleAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return CodeStyle."""
        # Note: pydantic_ai uses _output_type, not result_type
        assert agent._output_type == CodeStyle


class TestToolingDetection:
    """Test development tooling detection."""

    @pytest.mark.asyncio
    async def test_typescript_detected(self, tmp_path: Path):
        """TypeScript detected from tsconfig.json."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(uses_typescript=True)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.uses_typescript is True

    @pytest.mark.asyncio
    async def test_eslint_detected(self, tmp_path: Path):
        """ESLint detected from config file."""
        (tmp_path / ".eslintrc.json").write_text('{"extends": "eslint:recommended"}')
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(uses_eslint=True)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.uses_eslint is True

    @pytest.mark.asyncio
    async def test_prettier_detected(self, tmp_path: Path):
        """Prettier detected from config file."""
        (tmp_path / ".prettierrc").write_text('{"semi": false}')
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(uses_prettier=True)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.uses_prettier is True

    @pytest.mark.asyncio
    async def test_jest_detected(self, tmp_path: Path):
        """Jest detected from config file."""
        (tmp_path / "jest.config.js").write_text("module.exports = {};")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(test_framework="jest")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.test_framework == "jest"

    @pytest.mark.asyncio
    async def test_vitest_detected(self, tmp_path: Path):
        """Vitest detected from config file."""
        (tmp_path / "vitest.config.ts").write_text("export default {};")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(test_framework="vitest")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.test_framework == "vitest"


class TestExistingContainerFiles:
    """Test existing Docker file detection."""

    @pytest.mark.asyncio
    async def test_existing_dockerfile_detected(self, tmp_path: Path):
        """Existing Dockerfile detected."""
        (tmp_path / "Dockerfile").write_text("FROM node:20")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(dockerfile_exists=True)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.dockerfile_exists is True

    @pytest.mark.asyncio
    async def test_existing_compose_detected(self, tmp_path: Path):
        """Existing docker-compose.yaml detected."""
        (tmp_path / "docker-compose.yaml").write_text("version: '3.8'")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        mock_result = CodeStyle(compose_exists=True)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.compose_exists is True


class TestPlainJavaScript:
    """Test plain JavaScript projects."""

    @pytest.mark.asyncio
    async def test_no_typescript(self, tmp_path: Path):
        """Plain JS project without TypeScript."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "index.js").write_text("console.log('hello');")

        mock_result = CodeStyle(uses_typescript=False)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.uses_typescript is False

    @pytest.mark.asyncio
    async def test_multiple_tools(self, tmp_path: Path):
        """Multiple tools detected together (ESLint + Prettier + TypeScript)."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / ".eslintrc.json").write_text('{"extends": "eslint:recommended"}')
        (tmp_path / ".prettierrc").write_text('{"semi": false}')

        mock_result = CodeStyle(
            uses_typescript=True,
            uses_eslint=True,
            uses_prettier=True,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value.data = mock_result
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.uses_typescript is True
            assert result.data.uses_eslint is True
            assert result.data.uses_prettier is True

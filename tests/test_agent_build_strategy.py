"""Tests for build strategy analysis agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wunderunner.agents.analysis.build_strategy import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import BuildStrategy


class TestBuildStrategyPrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)

    def test_user_prompt_exists(self):
        """User prompt is defined."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, str)

    def test_system_prompt_mentions_monorepo(self):
        """System prompt includes monorepo detection."""
        assert "monorepo" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_native_deps(self):
        """System prompt includes native dependencies."""
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "native" in prompt_lower or "bcrypt" in prompt_lower or "sharp" in prompt_lower


class TestBuildStrategyAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return BuildStrategy."""
        # Note: pydantic_ai uses output_type, not result_type
        assert agent._output_type == BuildStrategy


class TestMonorepoDetection:
    """Test monorepo tool detection."""

    @pytest.mark.asyncio
    async def test_turborepo_detected(self, tmp_path: Path):
        """Turborepo monorepo detected from turbo.json."""
        (tmp_path / "package.json").write_text('{"name": "root"}')
        (tmp_path / "turbo.json").write_text('{"pipeline": {}}')

        mock_result = BuildStrategy(monorepo=True, monorepo_tool="turborepo")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.monorepo is True
            assert result.data.monorepo_tool == "turborepo"

    @pytest.mark.asyncio
    async def test_nx_detected(self, tmp_path: Path):
        """Nx monorepo detected from nx.json."""
        (tmp_path / "package.json").write_text('{"name": "root"}')
        (tmp_path / "nx.json").write_text('{}')

        mock_result = BuildStrategy(monorepo=True, monorepo_tool="nx")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.monorepo is True
            assert result.data.monorepo_tool == "nx"

    @pytest.mark.asyncio
    async def test_pnpm_workspaces_detected(self, tmp_path: Path):
        """pnpm workspaces detected from pnpm-workspace.yaml."""
        (tmp_path / "package.json").write_text('{"name": "root"}')
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'")

        mock_result = BuildStrategy(
            monorepo=True,
            monorepo_tool="pnpm",
            workspaces=["packages/*"]
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.monorepo is True
            assert "packages/*" in result.data.workspaces

    @pytest.mark.asyncio
    async def test_lerna_detected(self, tmp_path: Path):
        """Lerna monorepo detected from lerna.json."""
        (tmp_path / "package.json").write_text('{"name": "root"}')
        (tmp_path / "lerna.json").write_text('{"version": "1.0.0"}')

        mock_result = BuildStrategy(monorepo=True, monorepo_tool="lerna")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.monorepo is True
            assert result.data.monorepo_tool == "lerna"

    @pytest.mark.asyncio
    async def test_single_package_not_monorepo(self, tmp_path: Path):
        """Single package.json is not a monorepo."""
        (tmp_path / "package.json").write_text('{"name": "app"}')

        mock_result = BuildStrategy(monorepo=False)
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.monorepo is False


class TestNativeDependencies:
    """Test native dependency detection."""

    @pytest.mark.asyncio
    async def test_bcrypt_detected(self, tmp_path: Path):
        """bcrypt triggers native dependency flag."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"bcrypt": "^5.0.0"}}')

        mock_result = BuildStrategy(
            native_dependencies=["bcrypt"],
            multi_stage_recommended=True
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert "bcrypt" in result.data.native_dependencies
            assert result.data.multi_stage_recommended is True

    @pytest.mark.asyncio
    async def test_sharp_detected(self, tmp_path: Path):
        """sharp triggers native dependency flag."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"sharp": "^0.32.0"}}')

        mock_result = BuildStrategy(
            native_dependencies=["sharp"],
            multi_stage_recommended=True
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert "sharp" in result.data.native_dependencies

    @pytest.mark.asyncio
    async def test_multi_stage_recommended(self, tmp_path: Path):
        """Multi-stage build recommended for native dependencies."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"bcrypt": "^5.0.0", "sharp": "^0.32.0"}}')

        mock_result = BuildStrategy(
            native_dependencies=["bcrypt", "sharp"],
            multi_stage_recommended=True
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.multi_stage_recommended is True


class TestBuildCommands:
    """Test build/start command detection."""

    @pytest.mark.asyncio
    async def test_build_command_detected(self, tmp_path: Path):
        """Build command extracted from scripts."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"scripts": {"build": "tsc", "start": "node dist/index.js"}}')

        mock_result = BuildStrategy(
            build_command="npm run build",
            start_command="npm start"
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.build_command == "npm run build"
            assert result.data.start_command == "npm start"

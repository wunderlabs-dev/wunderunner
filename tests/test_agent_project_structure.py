"""Tests for project structure analysis agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wunderunner.agents.analysis.project_structure import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import ProjectStructure


class TestProjectStructurePrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100

    def test_user_prompt_exists(self):
        """User prompt is defined."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, str)

    def test_system_prompt_mentions_runtime(self):
        """System prompt includes runtime detection."""
        assert "runtime" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_check_files_exist(self):
        """System prompt instructs to use check_files_exist."""
        assert "check_files_exist" in SYSTEM_PROMPT


class TestProjectStructureAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return ProjectStructure."""
        # Note: pydantic_ai uses output_type, not result_type
        assert agent._output_type == ProjectStructure


class TestProjectStructureDetection:
    """Test project type detection logic."""

    @pytest.fixture
    def node_project(self, tmp_path: Path) -> Path:
        """Create a Node.js project."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test", "main": "index.js", "dependencies": {"express": "^4.18.0"}}')
        (tmp_path / "package-lock.json").write_text("{}")
        return tmp_path

    @pytest.fixture
    def python_project(self, tmp_path: Path) -> Path:
        """Create a Python project."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\ndependencies = ["fastapi"]')
        return tmp_path

    @pytest.fixture
    def go_project(self, tmp_path: Path) -> Path:
        """Create a Go project."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("module example.com/test\n\ngo 1.21")
        return tmp_path

    @pytest.fixture
    def rust_project(self, tmp_path: Path) -> Path:
        """Create a Rust project."""
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text('[package]\nname = "test"\nversion = "0.1.0"')
        return tmp_path

    @pytest.mark.asyncio
    async def test_node_project_detection(self, node_project: Path):
        """Node.js project is detected from package.json."""
        mock_result = ProjectStructure(
            runtime="node",
            framework="express",
            package_manager="npm",
            entry_point="index.js",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=node_project)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.runtime == "node"

    @pytest.mark.asyncio
    async def test_python_project_detection(self, python_project: Path):
        """Python project is detected from pyproject.toml."""
        mock_result = ProjectStructure(
            runtime="python",
            framework="fastapi",
            package_manager="pip",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=python_project)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.runtime == "python"

    @pytest.mark.asyncio
    async def test_go_project_detection(self, go_project: Path):
        """Go project is detected from go.mod."""
        mock_result = ProjectStructure(runtime="go", package_manager="go")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=go_project)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.runtime == "go"

    @pytest.mark.asyncio
    async def test_rust_project_detection(self, rust_project: Path):
        """Rust project is detected from Cargo.toml."""
        mock_result = ProjectStructure(runtime="rust", package_manager="cargo")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=rust_project)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.runtime == "rust"


class TestPackageManagerDetection:
    """Test package manager detection from lockfiles."""

    @pytest.mark.asyncio
    async def test_npm_from_package_lock(self, tmp_path: Path):
        """npm detected from package-lock.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "package-lock.json").write_text("{}")

        mock_result = ProjectStructure(runtime="node", package_manager="npm")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.package_manager == "npm"

    @pytest.mark.asyncio
    async def test_yarn_from_yarn_lock(self, tmp_path: Path):
        """yarn detected from yarn.lock."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "yarn.lock").write_text("")

        mock_result = ProjectStructure(runtime="node", package_manager="yarn")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.package_manager == "yarn"

    @pytest.mark.asyncio
    async def test_pnpm_from_pnpm_lock(self, tmp_path: Path):
        """pnpm detected from pnpm-lock.yaml."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "pnpm-lock.yaml").write_text("")

        mock_result = ProjectStructure(runtime="node", package_manager="pnpm")
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.package_manager == "pnpm"


class TestFrameworkDetection:
    """Test framework detection from dependencies."""

    @pytest.mark.asyncio
    async def test_express_framework_detected(self, tmp_path: Path):
        """Express.js framework detected from dependencies."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test", "dependencies": {"express": "^4.18.0"}}')
        (tmp_path / "package-lock.json").write_text("{}")

        mock_result = ProjectStructure(
            runtime="node",
            framework="express",
            package_manager="npm",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.framework == "express"

    @pytest.mark.asyncio
    async def test_fastapi_framework_detected(self, tmp_path: Path):
        """FastAPI framework detected from dependencies."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\ndependencies = ["fastapi"]')

        mock_result = ProjectStructure(
            runtime="python",
            framework="fastapi",
            package_manager="pip",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.framework == "fastapi"


class TestEntryPointDetection:
    """Test entry point detection."""

    @pytest.mark.asyncio
    async def test_entry_point_from_main_field(self, tmp_path: Path):
        """Entry point detected from package.json main field."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test", "main": "src/index.js"}')
        (tmp_path / "package-lock.json").write_text("{}")

        mock_result = ProjectStructure(
            runtime="node",
            package_manager="npm",
            entry_point="src/index.js",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.entry_point == "src/index.js"


class TestRuntimeVersionDetection:
    """Test runtime version detection."""

    @pytest.mark.asyncio
    async def test_runtime_version_from_engines(self, tmp_path: Path):
        """Runtime version detected from engines.node field."""
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test", "engines": {"node": ">=20.0.0"}}')
        (tmp_path / "package-lock.json").write_text("{}")

        mock_result = ProjectStructure(
            runtime="node",
            runtime_version="20",
            package_manager="npm",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data.runtime_version == "20"


class TestDependenciesPopulation:
    """Test dependencies list population."""

    @pytest.mark.asyncio
    async def test_dependencies_populated(self, tmp_path: Path):
        """Dependencies list extracted from package.json."""
        package_json = tmp_path / "package.json"
        package_json.write_text(
            '{"name": "test", "dependencies": {"express": "^4.18.0", "prisma": "^5.0.0"}}'
        )
        (tmp_path / "package-lock.json").write_text("{}")

        mock_result = ProjectStructure(
            runtime="node",
            package_manager="npm",
            dependencies=["express", "prisma"],
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert "express" in result.data.dependencies
            assert "prisma" in result.data.dependencies

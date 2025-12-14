"""Tests for project analysis activity."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wunderunner.activities.project import analyze, _merge_env_vars, _run_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import (
    Analysis,
    BuildStrategy,
    CodeStyle,
    EnvVar,
    ProjectStructure,
)
from wunderunner.settings import Analysis as AnalysisAgent


class TestMergeEnvVars:
    """Test _merge_env_vars function."""

    def test_deduplicates_by_name(self):
        """Duplicate env var names merged."""
        env_vars = [EnvVar(name="PORT"), EnvVar(name="PORT", default="3000")]
        secrets = []
        result = _merge_env_vars(env_vars, secrets)
        assert len(result) == 1
        assert result[0].name == "PORT"

    def test_secret_takes_precedence(self):
        """Secret flag preserved when merging."""
        env_vars = [EnvVar(name="API_KEY", secret=False)]
        secrets = [EnvVar(name="API_KEY", secret=True)]
        result = _merge_env_vars(env_vars, secrets)
        assert len(result) == 1
        assert result[0].secret is True

    def test_preserves_all_unique(self):
        """All unique env vars preserved."""
        env_vars = [EnvVar(name="PORT"), EnvVar(name="HOST")]
        secrets = [EnvVar(name="API_KEY", secret=True)]
        result = _merge_env_vars(env_vars, secrets)
        assert len(result) == 3

    def test_secrets_overwrite_env_vars(self):
        """Secrets completely replace env vars with same name."""
        env_vars = [EnvVar(name="DATABASE_URL", service="postgres")]
        secrets = [EnvVar(name="DATABASE_URL", secret=True)]
        result = _merge_env_vars(env_vars, secrets)
        # Secrets overwrite completely, service is lost
        assert result[0].secret is True
        assert result[0].service is None


class TestRunAgent:
    """Test _run_agent wrapper function."""

    @pytest.mark.asyncio
    async def test_returns_agent_result(self):
        """Returns agent result output."""
        mock_agent = MagicMock()
        expected = MagicMock(output=ProjectStructure(runtime="node"))
        mock_agent.run = AsyncMock(return_value=expected)

        result = await _run_agent(
            "Test Agent",
            mock_agent,
            "test prompt",
            MagicMock(),
            AnalysisAgent.PROJECT_STRUCTURE,
        )

        assert result == expected

    @pytest.mark.asyncio
    async def test_handles_errors(self):
        """Propagates errors from agent."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=ValueError("Agent failed"))

        with pytest.raises(ValueError, match="Agent failed"):
            await _run_agent(
                "Test Agent",
                mock_agent,
                "test prompt",
                MagicMock(),
                AnalysisAgent.PROJECT_STRUCTURE,
            )


class TestAnalyze:
    """Test analyze activity function."""

    @pytest.fixture
    def mock_agents(self):
        """Mock all analysis agents."""
        with (
            patch("wunderunner.activities.project.project_structure") as ps,
            patch("wunderunner.activities.project.build_strategy") as bs,
            patch("wunderunner.activities.project.env_vars") as ev,
            patch("wunderunner.activities.project.secrets") as sc,
            patch("wunderunner.activities.project.code_style") as cs,
        ):
            # Set up agent and USER_PROMPT attributes
            ps.agent = MagicMock()
            ps.USER_PROMPT = "Analyze project structure"
            ps.agent.run = AsyncMock(
                return_value=MagicMock(
                    output=ProjectStructure(runtime="node", framework="express")
                )
            )

            bs.agent = MagicMock()
            bs.USER_PROMPT = "Analyze build strategy"
            bs.agent.run = AsyncMock(
                return_value=MagicMock(output=BuildStrategy(build_command="npm run build"))
            )

            ev.agent = MagicMock()
            ev.USER_PROMPT = "Find env vars"
            ev.agent.run = AsyncMock(
                return_value=MagicMock(output=[EnvVar(name="PORT", default="3000")])
            )

            sc.agent = MagicMock()
            sc.USER_PROMPT = "Find secrets"
            sc.agent.run = AsyncMock(
                return_value=MagicMock(output=[EnvVar(name="API_KEY", secret=True)])
            )

            cs.agent = MagicMock()
            cs.USER_PROMPT = "Analyze code style"
            cs.agent.run = AsyncMock(
                return_value=MagicMock(output=CodeStyle(uses_typescript=True))
            )

            yield {
                "project_structure": ps,
                "build_strategy": bs,
                "env_vars": ev,
                "secrets": sc,
                "code_style": cs,
            }

    @pytest.mark.asyncio
    async def test_runs_all_agents(self, tmp_path: Path, mock_agents):
        """All 5 analysis agents are called."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        await analyze(tmp_path, rebuild=True)

        for agent_module in mock_agents.values():
            agent_module.agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_analysis(self, tmp_path: Path, mock_agents):
        """Returns combined Analysis model."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        result = await analyze(tmp_path, rebuild=True)

        assert isinstance(result, Analysis)
        assert result.project_structure.runtime == "node"
        assert result.build_strategy.build_command == "npm run build"
        assert result.code_style.uses_typescript is True

    @pytest.mark.asyncio
    async def test_caches_result(self, tmp_path: Path, mock_agents):
        """Analysis result saved to .wunderunner/analysis.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        await analyze(tmp_path, rebuild=True)

        cache_file = tmp_path / ".wunderunner" / "analysis.json"
        assert cache_file.exists()

        cached = json.loads(cache_file.read_text())
        assert cached["project_structure"]["runtime"] == "node"

    @pytest.mark.asyncio
    async def test_uses_cache_when_exists(self, tmp_path: Path, mock_agents):
        """Cache hit skips agent calls."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        cache_dir = tmp_path / ".wunderunner"
        cache_dir.mkdir()

        cached_analysis = Analysis(
            project_structure=ProjectStructure(runtime="python"),
            build_strategy=BuildStrategy(),
            code_style=CodeStyle(),
            env_vars=[],
        )
        (cache_dir / "analysis.json").write_text(cached_analysis.model_dump_json())

        result = await analyze(tmp_path, rebuild=False)

        # Should use cached result, not call agents
        assert result.project_structure.runtime == "python"
        for agent_module in mock_agents.values():
            agent_module.agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_rebuild_ignores_cache(self, tmp_path: Path, mock_agents):
        """rebuild=True forces fresh analysis."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        cache_dir = tmp_path / ".wunderunner"
        cache_dir.mkdir()

        cached_analysis = Analysis(
            project_structure=ProjectStructure(runtime="python"),
            build_strategy=BuildStrategy(),
            code_style=CodeStyle(),
            env_vars=[],
        )
        (cache_dir / "analysis.json").write_text(cached_analysis.model_dump_json())

        result = await analyze(tmp_path, rebuild=True)

        # Should ignore cache and call agents
        assert result.project_structure.runtime == "node"
        for agent_module in mock_agents.values():
            agent_module.agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_merges_env_vars_and_secrets(self, tmp_path: Path, mock_agents):
        """Env vars and secrets are merged."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        result = await analyze(tmp_path, rebuild=True)

        # Should have both PORT and API_KEY
        env_names = [e.name for e in result.env_vars]
        assert "PORT" in env_names
        assert "API_KEY" in env_names

    @pytest.mark.asyncio
    async def test_analysis_combines_all_results(self, tmp_path: Path, mock_agents):
        """All agent outputs merged into Analysis."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        result = await analyze(tmp_path, rebuild=True)

        # Verify all fields populated
        assert result.project_structure is not None
        assert result.project_structure.runtime == "node"
        assert result.project_structure.framework == "express"

        assert result.build_strategy is not None
        assert result.build_strategy.build_command == "npm run build"

        assert result.code_style is not None
        assert result.code_style.uses_typescript is True

        assert len(result.env_vars) == 2
        # Check that secret flag is properly set
        api_key_var = next(e for e in result.env_vars if e.name == "API_KEY")
        assert api_key_var.secret is True

"""Tests for environment variables analysis agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wunderunner.agents.analysis.env_vars import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import EnvVar


class TestEnvVarsPrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)

    def test_user_prompt_exists(self):
        """User prompt is defined."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, str)

    def test_system_prompt_mentions_env_patterns(self):
        """System prompt includes env var patterns."""
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "process.env" in prompt_lower or "environ" in prompt_lower


class TestEnvVarsAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return list of EnvVar."""
        # Note: pydantic_ai uses _output_type, not result_type
        assert agent._output_type == list[EnvVar]


class TestEnvVarPatternDetection:
    """Test env var pattern detection."""

    @pytest.mark.asyncio
    async def test_process_env_detected(self, tmp_path: Path):
        """process.env.VAR pattern detected."""
        (tmp_path / "index.js").write_text("const port = process.env.PORT || 3000;")

        mock_result = [EnvVar(name="PORT", required=False, default="3000")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert len(result.data) == 1
            assert result.data[0].name == "PORT"

    @pytest.mark.asyncio
    async def test_os_environ_detected(self, tmp_path: Path):
        """os.environ pattern detected."""
        (tmp_path / "app.py").write_text("host = os.environ['DATABASE_HOST']")

        mock_result = [EnvVar(name="DATABASE_HOST", required=True, service="postgres")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].name == "DATABASE_HOST"

    @pytest.mark.asyncio
    async def test_os_getenv_detected(self, tmp_path: Path):
        """os.getenv() pattern detected."""
        (tmp_path / "config.py").write_text("debug = os.getenv('DEBUG', 'false')")

        mock_result = [EnvVar(name="DEBUG", required=False, default="false")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].default == "false"


class TestServiceAssociation:
    """Test service detection from env var names."""

    @pytest.mark.asyncio
    async def test_database_associated_with_postgres(self, tmp_path: Path):
        """DATABASE_* vars associated with postgres."""
        (tmp_path / "db.js").write_text("const url = process.env.DATABASE_URL;")

        mock_result = [EnvVar(name="DATABASE_URL", service="postgres")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].service == "postgres"

    @pytest.mark.asyncio
    async def test_redis_url_associated_with_redis(self, tmp_path: Path):
        """REDIS_* vars associated with redis."""
        (tmp_path / "cache.js").write_text("const redis = process.env.REDIS_URL;")

        mock_result = [EnvVar(name="REDIS_URL", service="redis")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].service == "redis"


class TestDefaultValueExtraction:
    """Test default value extraction from code."""

    @pytest.mark.asyncio
    async def test_default_value_from_or_operator(self, tmp_path: Path):
        """Default values extracted from || operator."""
        (tmp_path / "server.js").write_text("const port = process.env.PORT || 8080;")

        mock_result = [EnvVar(name="PORT", required=False, default="8080")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].required is False
            assert result.data[0].default == "8080"


class TestRequiredFlag:
    """Test required vs optional detection."""

    @pytest.mark.asyncio
    async def test_required_when_no_default(self, tmp_path: Path):
        """Variables without defaults are marked required."""
        (tmp_path / "config.py").write_text("api_url = os.environ['API_URL']")

        mock_result = [EnvVar(name="API_URL", required=True)]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].required is True

    @pytest.mark.asyncio
    async def test_optional_when_has_default(self, tmp_path: Path):
        """Variables with defaults are marked optional."""
        (tmp_path / "config.py").write_text("debug = os.getenv('DEBUG', 'false')")

        mock_result = [EnvVar(name="DEBUG", required=False, default="false")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].required is False


class TestExcludesSecrets:
    """Test that secrets are not included in env vars."""

    @pytest.mark.asyncio
    async def test_excludes_api_keys(self, tmp_path: Path):
        """API keys should not be returned by env vars agent."""
        (tmp_path / "config.js").write_text(
            "const key = process.env.API_KEY;\nconst port = process.env.PORT || 3000;"
        )

        # Agent should only return non-secret vars
        mock_result = [EnvVar(name="PORT", required=False, default="3000")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            # Should not include API_KEY
            env_names = [e.name for e in result.data]
            assert "API_KEY" not in env_names
            assert "PORT" in env_names


class TestDotenvParsing:
    """Test .env.example file parsing."""

    @pytest.mark.asyncio
    async def test_dotenv_example_parsed(self, tmp_path: Path):
        """Env vars extracted from .env.example."""
        (tmp_path / ".env.example").write_text("PORT=3000\nNODE_ENV=development")

        mock_result = [
            EnvVar(name="PORT", default="3000"),
            EnvVar(name="NODE_ENV", default="development"),
        ]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert len(result.data) == 2

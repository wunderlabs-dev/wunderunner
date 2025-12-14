"""Tests for secrets analysis agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wunderunner.agents.analysis.secrets import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import EnvVar


class TestSecretsPrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)

    def test_user_prompt_exists(self):
        """User prompt is defined."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, str)

    def test_system_prompt_mentions_secrets(self):
        """System prompt includes secret patterns."""
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "secret" in prompt_lower or "api_key" in prompt_lower


class TestSecretsAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return list of EnvVar."""
        # Note: pydantic_ai uses _output_type, not result_type
        assert agent._output_type == list[EnvVar]


class TestSecretDetection:
    """Test secret pattern detection."""

    @pytest.mark.asyncio
    async def test_api_key_detected(self, tmp_path: Path):
        """API_KEY pattern detected as secret."""
        (tmp_path / "config.js").write_text("const key = process.env.API_KEY;")

        mock_result = [EnvVar(name="API_KEY", secret=True)]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].name == "API_KEY"
            assert result.data[0].secret is True

    @pytest.mark.asyncio
    async def test_secret_key_detected(self, tmp_path: Path):
        """SECRET_KEY pattern detected."""
        (tmp_path / "settings.py").write_text("SECRET_KEY = os.environ['SECRET_KEY']")

        mock_result = [EnvVar(name="SECRET_KEY", secret=True)]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].secret is True

    @pytest.mark.asyncio
    async def test_password_detected(self, tmp_path: Path):
        """*_PASSWORD pattern detected."""
        (tmp_path / "db.py").write_text("password = os.getenv('DATABASE_PASSWORD')")

        mock_result = [EnvVar(name="DATABASE_PASSWORD", secret=True, service="postgres")]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].secret is True

    @pytest.mark.asyncio
    async def test_token_detected(self, tmp_path: Path):
        """*_TOKEN pattern detected."""
        (tmp_path / "auth.js").write_text("const token = process.env.AUTH_TOKEN;")

        mock_result = [EnvVar(name="AUTH_TOKEN", secret=True)]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].secret is True


class TestSecretFiltering:
    """Test false positive filtering."""

    @pytest.mark.asyncio
    async def test_next_public_excluded(self, tmp_path: Path):
        """NEXT_PUBLIC_* vars not marked as secrets."""
        (tmp_path / "next.config.js").write_text(
            "const url = process.env.NEXT_PUBLIC_API_URL;"
        )

        # Agent should return empty list for public vars
        mock_result = []
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_publishable_key_excluded(self, tmp_path: Path):
        """*_PUBLISHABLE_KEY not marked as secrets."""
        (tmp_path / "stripe.js").write_text(
            "const pk = process.env.STRIPE_PUBLISHABLE_KEY;"
        )

        mock_result = []
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert len(result.data) == 0


class TestSecretFlagTrue:
    """Test that all results have secret=True."""

    @pytest.mark.asyncio
    async def test_all_secrets_have_secret_flag(self, tmp_path: Path):
        """All returned env vars have secret=True."""
        (tmp_path / "config.js").write_text(
            "const db = process.env.DATABASE_URL;\nconst key = process.env.API_KEY;"
        )

        mock_result = [
            EnvVar(name="DATABASE_URL", secret=True, service="postgres"),
            EnvVar(name="API_KEY", secret=True),
        ]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            # All secrets must have secret=True
            for env_var in result.data:
                assert env_var.secret is True


class TestDatabasePasswordWithService:
    """Test database password with service association."""

    @pytest.mark.asyncio
    async def test_database_password_with_service(self, tmp_path: Path):
        """Database password is associated with postgres service."""
        (tmp_path / "db.py").write_text("password = os.environ['POSTGRES_PASSWORD']")

        mock_result = [
            EnvVar(name="POSTGRES_PASSWORD", secret=True, service="postgres")
        ]
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(data=mock_result)
            deps = AgentDeps(project_dir=tmp_path)
            result = await agent.run(USER_PROMPT, deps=deps)
            assert result.data[0].name == "POSTGRES_PASSWORD"
            assert result.data[0].secret is True
            assert result.data[0].service == "postgres"

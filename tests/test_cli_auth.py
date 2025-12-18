"""Tests for CLI auth commands."""

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from wunderunner.cli.main import app

runner = CliRunner()


class TestAuthStatus:
    """Test wxr auth status command."""

    def test_shows_no_auth_when_empty(self):
        """Status shows no authentication when store is empty."""
        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore()

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = None
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "not configured" in result.stdout.lower() or "none" in result.stdout.lower()

    def test_shows_oauth_when_tokens_exist(self):
        """Status shows OAuth when tokens are configured."""
        import time

        from wunderunner.auth.models import AuthStore, TokenSet

        tokens = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AuthStore(anthropic=tokens)

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = None
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "oauth" in result.stdout.lower()

    def test_shows_api_key_when_env_set(self):
        """Status shows API key when environment variable is set."""
        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore()

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "sk-ant-xxx"
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "api key" in result.stdout.lower() or "env" in result.stdout.lower()


class TestAuthLogout:
    """Test wxr auth logout command."""

    def test_logout_clears_tokens(self):
        """Logout clears tokens for selected provider."""
        with (
            patch("wunderunner.cli.auth.clear_tokens", new_callable=AsyncMock) as mock_clear,
            patch("wunderunner.cli.auth.Prompt.ask", return_value="1"),  # Select Anthropic
        ):
            result = runner.invoke(app, ["auth", "logout"])

            assert result.exit_code == 0
            mock_clear.assert_called_once()


class TestAuthLogin:
    """Test wxr auth login command."""

    def test_login_command_exists(self):
        """Login command is registered."""
        result = runner.invoke(app, ["auth", "login", "--help"])
        assert result.exit_code == 0
        assert "login" in result.stdout.lower()

"""Integration tests for service detection activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import service_detection
from wunderunner.models.analysis import DetectedService, EnvVar, ServiceConfig


class TestDetectServices:
    """Integration tests for service_detection.detect_services()."""

    @pytest.mark.asyncio
    async def test_empty_env_vars_returns_empty_list(self):
        """No env vars returns empty list without calling agent."""
        with patch("wunderunner.activities.service_detection.services_agent") as mock_agent:
            result = await service_detection.detect_services([])

            assert result == []
            mock_agent.agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_detects_postgres_from_database_url(self):
        """Detects postgres service from DATABASE_URL env var."""
        env_vars = [
            EnvVar(name="DATABASE_URL", required=True),
            EnvVar(name="PORT", required=False, default="3000"),
        ]

        mock_detected = [
            DetectedService(
                type="postgres",
                env_vars=["DATABASE_URL"],
                confidence=0.9,
            )
        ]
        mock_result = MagicMock()
        mock_result.output = mock_detected

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await service_detection.detect_services(env_vars)

            assert len(result) == 1
            assert result[0].type == "postgres"
            assert "DATABASE_URL" in result[0].env_vars

    @pytest.mark.asyncio
    async def test_detects_multiple_services(self):
        """Detects multiple services from env vars."""
        env_vars = [
            EnvVar(name="DATABASE_URL", required=True),
            EnvVar(name="REDIS_URL", required=True),
        ]

        mock_detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]
        mock_result = MagicMock()
        mock_result.output = mock_detected

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await service_detection.detect_services(env_vars)

            assert len(result) == 2
            types = [s.type for s in result]
            assert "postgres" in types
            assert "redis" in types

    @pytest.mark.asyncio
    async def test_agent_error_returns_empty_list(self):
        """Agent failure returns empty list gracefully."""
        env_vars = [EnvVar(name="DATABASE_URL", required=True)]

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API error"))

            result = await service_detection.detect_services(env_vars)

            # Should return empty list, not raise
            assert result == []


class TestConfirmServices:
    """Tests for service_detection.confirm_services()."""

    def test_all_confirmed_returns_all(self):
        """All confirmed services are returned as ServiceConfig."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]

        def always_confirm(service_type: str, env_vars: list[str]) -> bool:
            return True

        result = service_detection.confirm_services(detected, always_confirm)

        assert len(result) == 2
        assert all(isinstance(s, ServiceConfig) for s in result)
        types = [s.type for s in result]
        assert "postgres" in types
        assert "redis" in types

    def test_none_confirmed_returns_empty(self):
        """No confirmed services returns empty list."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
        ]

        def never_confirm(service_type: str, env_vars: list[str]) -> bool:
            return False

        result = service_detection.confirm_services(detected, never_confirm)

        assert result == []

    def test_partial_confirmation(self):
        """Only confirmed services are returned."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]

        def confirm_postgres_only(service_type: str, env_vars: list[str]) -> bool:
            return service_type == "postgres"

        result = service_detection.confirm_services(detected, confirm_postgres_only)

        assert len(result) == 1
        assert result[0].type == "postgres"

    def test_env_vars_preserved_in_service_config(self):
        """Env vars are preserved in ServiceConfig."""
        detected = [
            DetectedService(
                type="postgres",
                env_vars=["DATABASE_URL", "DB_HOST", "DB_PORT"],
                confidence=0.9,
            ),
        ]

        def always_confirm(service_type: str, env_vars: list[str]) -> bool:
            return True

        result = service_detection.confirm_services(detected, always_confirm)

        assert result[0].env_vars == ["DATABASE_URL", "DB_HOST", "DB_PORT"]

    def test_callback_receives_correct_args(self):
        """Callback receives service type and env vars."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
        ]

        received_calls = []

        def tracking_callback(service_type: str, env_vars: list[str]) -> bool:
            received_calls.append((service_type, env_vars))
            return True

        service_detection.confirm_services(detected, tracking_callback)

        assert len(received_calls) == 1
        assert received_calls[0] == ("postgres", ["DATABASE_URL"])

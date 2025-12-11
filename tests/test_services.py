"""Integration tests for services activities."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wunderunner.activities import services
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError


@pytest.fixture
def mock_container():
    """Create a mock container with configurable state."""
    def _make_container(
        container_id: str = "abc123",
        status: str = "running",
        name: str = "test-container",
        ports: dict | None = None,
        logs: bytes = b"container logs here",
    ):
        container = MagicMock()
        container.id = container_id
        container.status = status
        container.name = name
        container.logs.return_value = logs
        container.attrs = {
            "NetworkSettings": {
                "Ports": ports or {}
            }
        }
        return container
    return _make_container


@pytest.fixture
def mock_docker_client(mock_container):
    """Create a mock Docker client."""
    client = MagicMock()
    container = mock_container()
    client.containers.get.return_value = container
    return client


class TestHealthcheck:
    """Tests for healthcheck function."""

    @pytest.mark.asyncio
    async def test_empty_container_list_raises_error(self):
        """Healthcheck with no containers should raise HealthcheckError."""
        with pytest.raises(HealthcheckError, match="No containers to check"):
            await services.healthcheck([])

    @pytest.mark.asyncio
    async def test_happy_path_containers_running_http_success(self, mock_container):
        """Healthcheck passes when containers run and HTTP returns 200."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.return_value = mock_response
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            # Should complete without raising
            await services.healthcheck(["abc123"], timeout=5)

    @pytest.mark.asyncio
    async def test_container_exits_raises_error(self, mock_container):
        """Healthcheck fails when container exits."""
        container = mock_container(
            status="exited",
            logs=b"Error: process crashed",
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with patch("wunderunner.activities.services.get_client", return_value=mock_client):
            with pytest.raises(HealthcheckError, match="exited"):
                await services.healthcheck(["abc123"], timeout=5)

    @pytest.mark.asyncio
    async def test_timeout_waiting_for_containers(self, mock_container):
        """Healthcheck times out if containers never reach running state."""
        container = mock_container(status="created")  # Never becomes running
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(HealthcheckError, match="timed out.*waiting for containers"):
                await services.healthcheck(["abc123"], timeout=1)

    @pytest.mark.asyncio
    async def test_timeout_waiting_for_http(self, mock_container):
        """Healthcheck times out if HTTP never responds."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.side_effect = httpx.RequestError("Connection refused")
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            with pytest.raises(HealthcheckError, match="timed out.*HTTP"):
                await services.healthcheck(["abc123"], timeout=1)

    @pytest.mark.asyncio
    async def test_http_500_error_fails_immediately(self, mock_container):
        """Healthcheck fails immediately on HTTP 500."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 500

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.return_value = mock_response
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            with pytest.raises(HealthcheckError, match="HTTP 500"):
                await services.healthcheck(["abc123"], timeout=5)

    @pytest.mark.asyncio
    async def test_no_http_ports_succeeds(self, mock_container):
        """Healthcheck passes when no ports exposed (skips HTTP phase)."""
        container = mock_container(status="running", ports={})
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        with patch("wunderunner.activities.services.get_client", return_value=mock_client):
            # Should complete without raising
            await services.healthcheck(["abc123"], timeout=5)

    @pytest.mark.asyncio
    async def test_connection_refused_then_success(self, mock_container):
        """Healthcheck retries and succeeds after initial connection refused."""
        container = mock_container(
            status="running",
            ports={"8000/tcp": [{"HostPort": "8000"}]},
        )
        mock_client = MagicMock()
        mock_client.containers.get.return_value = container

        mock_response = MagicMock()
        mock_response.status_code = 200

        call_count = 0

        async def get_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.RequestError("Connection refused")
            return mock_response

        with (
            patch("wunderunner.activities.services.get_client", return_value=mock_client),
            patch("httpx.AsyncClient") as mock_httpx,
            patch("wunderunner.activities.services.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_httpx_instance = AsyncMock()
            mock_httpx_instance.get.side_effect = get_with_retry
            mock_httpx.return_value.__aenter__.return_value = mock_httpx_instance

            await services.healthcheck(["abc123"], timeout=10)
            assert call_count >= 3


class TestStart:
    """Tests for start function."""

    @pytest.mark.asyncio
    async def test_compose_file_missing_raises_error(self, tmp_path):
        """Start raises error when docker-compose.yaml doesn't exist."""
        with pytest.raises(StartError, match="docker-compose.yaml not found"):
            await services.start(tmp_path)

    @pytest.mark.asyncio
    async def test_happy_path_returns_container_ids(self, tmp_path):
        """Start returns container IDs on success."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        async def mock_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        async def mock_subprocess_ps(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            # docker compose ps -q returns container IDs
            proc.communicate = AsyncMock(return_value=(b"container1\ncontainer2\n", b""))
            return proc

        call_count = 0

        async def create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First two calls are down and up, third is ps
            if call_count <= 2:
                return await mock_subprocess(*args, **kwargs)
            return await mock_subprocess_ps(*args, **kwargs)

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            result = await services.start(tmp_path)
            assert result == ["container1", "container2"]

    @pytest.mark.asyncio
    async def test_compose_up_fails_raises_error(self, tmp_path):
        """Start raises error when docker compose up fails."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        call_count = 0

        async def create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = MagicMock()
            if call_count == 1:
                # down succeeds
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:
                # up fails
                proc.returncode = 1
                proc.communicate = AsyncMock(return_value=(b"Error: build failed", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            with pytest.raises(StartError, match="docker compose up failed"):
                await services.start(tmp_path)

    @pytest.mark.asyncio
    async def test_no_containers_started_raises_error(self, tmp_path):
        """Start raises error when no containers are started."""
        compose_file = tmp_path / "docker-compose.yaml"
        compose_file.write_text("version: '3'\nservices:\n  app:\n    image: alpine\n")

        async def create_subprocess(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            # ps returns empty (no containers)
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_subprocess):
            with pytest.raises(StartError, match="No containers started"):
                await services.start(tmp_path)

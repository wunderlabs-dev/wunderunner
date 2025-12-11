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

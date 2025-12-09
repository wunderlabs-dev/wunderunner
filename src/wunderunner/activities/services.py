"""Services (docker-compose) activities."""

from dataclasses import dataclass
from pathlib import Path

from wunderunner.activities.project import Analysis
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError
from wunderunner.workflows.base import Learning


@dataclass
class ServicesConfig:
    """Docker compose configuration."""

    # TODO: Add actual config fields
    content: str = ""


async def generate(
    analysis: Analysis, dockerfile_content: str, learnings: list[Learning]
) -> ServicesConfig:
    """Generate docker-compose.yaml based on analysis and learnings.

    Raises:
        ServicesError: If generation fails.
    """
    # TODO: Implement with pydantic-ai agent
    raise NotImplementedError


async def start(path: Path) -> list[str]:
    """Start services with docker compose up.

    Returns:
        List of container IDs.

    Raises:
        StartError: If services fail to start.
    """
    # TODO: Implement with docker API
    raise NotImplementedError


async def stop(path: Path) -> None:
    """Stop services with docker compose down."""
    # TODO: Implement with docker API
    raise NotImplementedError


async def healthcheck(container_ids: list[str]) -> None:
    """Check health of running containers.

    Raises:
        HealthcheckError: If healthcheck fails.
    """
    # TODO: Implement log watching and health checks
    raise NotImplementedError

"""Services (docker-compose) activities."""

from pathlib import Path

from wunderunner.models.analysis import Analysis
from wunderunner.workflows.state import Learning


async def generate(
    analysis: Analysis,
    dockerfile_content: str,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
) -> str:
    """Generate or refine docker-compose.yaml based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        dockerfile_content: The Dockerfile being used.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this compose file instead of generating fresh.

    Returns:
        docker-compose.yaml content as string.

    Raises:
        ServicesError: If generation/refinement fails.
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

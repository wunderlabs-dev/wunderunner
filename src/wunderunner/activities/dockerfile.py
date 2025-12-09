"""Dockerfile generation activity."""

from wunderunner.activities.project import Analysis
from wunderunner.exceptions import DockerfileError
from wunderunner.workflows.base import Learning


async def generate(analysis: Analysis, learnings: list[Learning]) -> str:
    """Generate Dockerfile based on analysis and learnings.

    Returns:
        Dockerfile content as string.

    Raises:
        DockerfileError: If generation fails.
    """
    # TODO: Implement with pydantic-ai agent
    raise NotImplementedError

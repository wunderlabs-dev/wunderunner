"""Dockerfile generation activity."""

from wunderunner.models.analysis import Analysis
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

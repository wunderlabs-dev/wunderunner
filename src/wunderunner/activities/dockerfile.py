"""Dockerfile generation activity."""

from wunderunner.models.analysis import Analysis
from wunderunner.workflows.state import Learning


async def generate(
    analysis: Analysis,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
) -> str:
    """Generate or refine Dockerfile based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this Dockerfile instead of generating fresh.

    Returns:
        Dockerfile content as string.

    Raises:
        DockerfileError: If generation/refinement fails.
    """
    # TODO: Implement with pydantic-ai agent
    raise NotImplementedError

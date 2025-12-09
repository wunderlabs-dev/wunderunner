"""Docker image activities."""

from pathlib import Path


async def build(path: Path, dockerfile_content: str) -> str:
    """Build Docker image from dockerfile content.

    Returns:
        Image ID.

    Raises:
        BuildError: If build fails.
    """
    # TODO: Implement with docker API
    raise NotImplementedError

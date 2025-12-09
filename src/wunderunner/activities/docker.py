"""Docker image activities."""

import asyncio
import uuid
from pathlib import Path

from wunderunner.exceptions import BuildError
from wunderunner.settings import get_settings


async def build(path: Path, dockerfile_content: str) -> str:
    """Build Docker image from dockerfile content.

    Writes the Dockerfile to the project directory and runs docker build.

    Args:
        path: Path to the project directory (build context).
        dockerfile_content: The Dockerfile content to build.

    Returns:
        Image ID (sha256 hash).

    Raises:
        BuildError: If build fails.
    """
    settings = get_settings()
    dockerfile_path = path / settings.cache_dir / "Dockerfile"

    # Ensure cache directory exists
    dockerfile_path.parent.mkdir(parents=True, exist_ok=True)

    # Write Dockerfile
    dockerfile_path.write_text(dockerfile_content)

    # Generate a tag for this build
    tag = f"wunderunner-{uuid.uuid4().hex[:8]}"

    # Build command
    cmd = [
        "docker",
        "build",
        "-t",
        tag,
        "-f",
        str(dockerfile_path),
        str(path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, _ = await process.communicate()
    output = stdout.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise BuildError(f"Docker build failed:\n{output}")

    # Get the image ID
    image_id = await _get_image_id(tag)

    return image_id


async def _get_image_id(tag: str) -> str:
    """Get the image ID for a given tag."""
    cmd = ["docker", "images", "-q", tag]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()
    image_id = stdout.decode().strip()

    if not image_id:
        raise BuildError(f"Could not find image ID for tag: {tag}")

    return image_id

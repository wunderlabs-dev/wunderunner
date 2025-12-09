"""Docker image activities."""

import asyncio
import hashlib
from pathlib import Path

from wunderunner.exceptions import BuildError
from wunderunner.settings import get_settings


def _compute_cache_tag(path: Path, dockerfile_content: str) -> str:
    """Generate stable tag from project path and Dockerfile content.

    Uses hashes of both to create a unique, reproducible tag that allows
    cache hits when the same Dockerfile is used for the same project.
    """
    path_hash = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    content_hash = hashlib.sha256(dockerfile_content.encode()).hexdigest()[:8]
    return f"wunderunner-{path_hash}-{content_hash}"


async def _image_exists(tag: str) -> bool:
    """Check if a Docker image with this tag exists locally."""
    cmd = ["docker", "images", "-q", tag]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    return bool(stdout.decode().strip())


async def build(path: Path, dockerfile_content: str) -> tuple[str, bool]:
    """Build Docker image from dockerfile content, using cache if available.

    Writes the Dockerfile to the project directory and runs docker build.
    Uses content-based caching to skip rebuilds when Dockerfile is unchanged.

    Args:
        path: Path to the project directory (build context).
        dockerfile_content: The Dockerfile content to build.

    Returns:
        Tuple of (image_id, cache_hit). cache_hit is True if build was skipped.

    Raises:
        BuildError: If build fails.
    """
    settings = get_settings()
    dockerfile_path = path / settings.cache_dir / "Dockerfile"

    # Ensure cache directory exists
    dockerfile_path.parent.mkdir(parents=True, exist_ok=True)

    # Write Dockerfile
    dockerfile_path.write_text(dockerfile_content)

    # Generate stable tag for caching
    tag = _compute_cache_tag(path, dockerfile_content)

    # Check if image already exists (cache hit)
    if await _image_exists(tag):
        image_id = await _get_image_id(tag)
        return image_id, True

    # Build the image
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

    return image_id, False


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

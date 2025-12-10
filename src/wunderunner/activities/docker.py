"""Docker image activities using docker-py SDK."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import docker
from docker.errors import BuildError as DockerBuildError
from docker.errors import ImageNotFound

from wunderunner.exceptions import BuildError
from wunderunner.settings import get_settings


@dataclass
class BuildResult:
    """Result of a Docker build operation."""

    image_id: str
    cache_hit: bool


def _get_client() -> docker.DockerClient:
    """Get Docker client from environment."""
    return docker.from_env()


def _compute_cache_tag(path: Path, dockerfile_content: str) -> str:
    """Generate stable tag from project path and Dockerfile content.

    Uses hashes of both to create a unique, reproducible tag that allows
    cache hits when the same Dockerfile is used for the same project.
    """
    path_hash = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    content_hash = hashlib.sha256(dockerfile_content.encode()).hexdigest()[:8]
    return f"wunderunner-{path_hash}-{content_hash}"


def _image_exists(client: docker.DockerClient, tag: str) -> bool:
    """Check if a Docker image with this tag exists locally."""
    try:
        client.images.get(tag)
        return True
    except ImageNotFound:
        return False


async def build(path: Path, dockerfile_content: str) -> BuildResult:
    """Build Docker image from dockerfile content, using cache if available.

    Writes the Dockerfile to the project directory and runs docker build.
    Uses content-based caching to skip rebuilds when Dockerfile is unchanged.

    Args:
        path: Path to the project directory (build context).
        dockerfile_content: The Dockerfile content to build.

    Returns:
        BuildResult with image_id and cache_hit flag.

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

    client = _get_client()

    # Check if image already exists (cache hit)
    if _image_exists(client, tag):
        image = client.images.get(tag)
        return BuildResult(image_id=image.id, cache_hit=True)

    # Build the image
    try:
        image, _build_logs = client.images.build(
            path=str(path),
            dockerfile=str(dockerfile_path),
            tag=tag,
            rm=True,  # Remove intermediate containers
            forcerm=True,  # Always remove intermediate containers
        )
        return BuildResult(image_id=image.id, cache_hit=False)
    except DockerBuildError as e:
        # Extract build log from exception
        logs = []
        for chunk in e.build_log:
            if "stream" in chunk:
                logs.append(chunk["stream"])
            elif "error" in chunk:
                logs.append(chunk["error"])
        output = "".join(logs)
        raise BuildError(f"Docker build failed:\n{output}") from e
    except Exception as e:
        raise BuildError(f"Docker build failed: {e}") from e

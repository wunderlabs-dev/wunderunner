"""Write files from parsed plan to project directory."""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.implement.parser import ParsedPlan


async def write_files(project_dir: Path, plan: ParsedPlan) -> list[str]:
    """Write Dockerfile and docker-compose.yaml to project directory.

    Args:
        project_dir: Project root directory.
        plan: ParsedPlan with file contents.

    Returns:
        List of filenames that were written.
    """
    written: list[str] = []

    if plan.dockerfile:
        dockerfile_path = project_dir / "Dockerfile"
        async with aiofiles.open(dockerfile_path, "w") as f:
            await f.write(plan.dockerfile)
        written.append("Dockerfile")

    if plan.compose:
        compose_path = project_dir / "docker-compose.yaml"
        async with aiofiles.open(compose_path, "w") as f:
            await f.write(plan.compose)
        written.append("docker-compose.yaml")

    return written

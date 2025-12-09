"""Services (docker-compose) activities."""

import asyncio
from pathlib import Path

from wunderunner.agents.generation import compose as compose_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError
from wunderunner.models.analysis import Analysis
from wunderunner.settings import get_settings
from wunderunner.workflows.state import Learning


def _format_learnings(learnings: list[Learning]) -> str:
    """Format learnings for the prompt."""
    if not learnings:
        return "None"

    lines = []
    for learning in learnings:
        lines.append(f"- [{learning.phase}] {learning.error_type}: {learning.error_message}")
        if learning.context:
            lines.append(f"  Context: {learning.context}")
    return "\n".join(lines)


def _build_prompt(
    analysis: Analysis,
    dockerfile_content: str,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None,
) -> str:
    """Build the user prompt for the compose agent."""
    parts = []

    # Project analysis
    parts.append("<project_analysis>")
    parts.append(f"Runtime: {analysis.project_structure.runtime}")
    if analysis.project_structure.runtime_version:
        parts.append(f"Runtime Version: {analysis.project_structure.runtime_version}")
    if analysis.project_structure.framework:
        parts.append(f"Framework: {analysis.project_structure.framework}")
    parts.append(f"Package Manager: {analysis.project_structure.package_manager}")
    if analysis.project_structure.entry_point:
        parts.append(f"Entry Point: {analysis.project_structure.entry_point}")
    parts.append("</project_analysis>")

    # Environment variables
    if analysis.env_vars:
        parts.append("\n<environment_variables>")
        for var in analysis.env_vars:
            secret_marker = " [SECRET]" if var.secret else ""
            default_hint = f" (default: {var.default})" if var.default else ""
            service_hint = f" (service: {var.service})" if var.service else ""
            parts.append(f"- {var.name}{secret_marker}{default_hint}{service_hint}")
        parts.append("</environment_variables>")

    # Dockerfile being used
    parts.append("\n<dockerfile>")
    parts.append(dockerfile_content)
    parts.append("</dockerfile>")

    # Previous learnings
    parts.append("\n<previous_learnings>")
    parts.append(_format_learnings(learnings))
    parts.append("</previous_learnings>")

    # User hints
    if hints:
        parts.append("\n<user_hints>")
        for hint in hints:
            parts.append(f"- {hint}")
        parts.append("</user_hints>")

    # Existing compose file to refine
    if existing:
        parts.append("\n<existing_compose>")
        parts.append(existing)
        parts.append("</existing_compose>")
        parts.append("\nRefine the above docker-compose.yaml to fix the issues.")
    else:
        parts.append("\nGenerate a new docker-compose.yaml for this project.")

    return "\n".join(parts)


async def generate(
    analysis: Analysis,
    dockerfile_content: str,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
    project_path: Path | None = None,
) -> str:
    """Generate or refine docker-compose.yaml based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        dockerfile_content: The Dockerfile being used.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this compose file instead of generating fresh.
        project_path: Path to project directory (for tool access).

    Returns:
        docker-compose.yaml content as string.

    Raises:
        ServicesError: If generation/refinement fails.
    """
    prompt = _build_prompt(analysis, dockerfile_content, learnings, hints, existing)

    deps = AgentDeps(project_dir=project_path) if project_path else None

    try:
        result = await compose_agent.agent.run(prompt, deps=deps)
        return result.output
    except Exception as e:
        raise ServicesError(f"Failed to generate docker-compose.yaml: {e}") from e


async def start(path: Path) -> list[str]:
    """Start services with docker compose up.

    Writes the compose file to the project directory and runs docker compose up.

    Args:
        path: Path to the project directory.

    Returns:
        List of container IDs.

    Raises:
        StartError: If services fail to start.
    """
    settings = get_settings()
    compose_path = path / settings.cache_dir / "docker-compose.yaml"

    if not compose_path.exists():
        raise StartError("docker-compose.yaml not found. Run generate first.")

    # Run docker compose up in detached mode
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_path),
        "up",
        "-d",
        "--build",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(path),
    )

    stdout, _ = await process.communicate()
    output = stdout.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise StartError(f"docker compose up failed:\n{output}")

    # Get container IDs
    container_ids = await _get_container_ids(path)
    if not container_ids:
        raise StartError("No containers started")

    return container_ids


async def _get_container_ids(path: Path) -> list[str]:
    """Get container IDs for the running compose services."""
    settings = get_settings()
    compose_path = path / settings.cache_dir / "docker-compose.yaml"

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_path),
        "ps",
        "-q",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(path),
    )

    stdout, _ = await process.communicate()
    output = stdout.decode().strip()

    if not output:
        return []

    return output.split("\n")


async def stop(path: Path) -> None:
    """Stop services with docker compose down.

    Args:
        path: Path to the project directory.
    """
    settings = get_settings()
    compose_path = path / settings.cache_dir / "docker-compose.yaml"

    if not compose_path.exists():
        return

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_path),
        "down",
        "-v",  # Remove volumes
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(path),
    )

    await process.communicate()


async def healthcheck(container_ids: list[str], timeout: int = 60) -> None:
    """Check health of running containers.

    Waits for containers to be healthy or running for the specified timeout.

    Args:
        container_ids: List of container IDs to check.
        timeout: Maximum seconds to wait for healthy state.

    Raises:
        HealthcheckError: If healthcheck fails.
    """
    if not container_ids:
        raise HealthcheckError("No containers to check")

    start_time = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise HealthcheckError(f"Health check timed out after {timeout}s")

        all_healthy = True
        for container_id in container_ids:
            status = await _get_container_status(container_id)

            if status == "exited":
                logs = await _get_container_logs(container_id)
                raise HealthcheckError(f"Container {container_id[:12]} exited:\n{logs}")

            if status not in ("running", "healthy"):
                all_healthy = False

        if all_healthy:
            return

        await asyncio.sleep(2)


async def _get_container_status(container_id: str) -> str:
    """Get the status of a container."""
    cmd = [
        "docker",
        "inspect",
        "--format",
        "{{.State.Status}}",
        container_id,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()
    return stdout.decode().strip()


async def _get_container_logs(container_id: str, tail: int = 50) -> str:
    """Get recent logs from a container."""
    cmd = [
        "docker",
        "logs",
        "--tail",
        str(tail),
        container_id,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, _ = await process.communicate()
    return stdout.decode("utf-8", errors="replace")

"""Services (docker-compose) activities.

Uses docker-py SDK for container inspection and healthchecks.
Uses docker compose CLI for orchestration (no SDK support for compose).
"""

import asyncio
from pathlib import Path

import docker
import httpx
from docker.errors import NotFound

from wunderunner.agents.generation import compose as compose_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError
from wunderunner.models.analysis import Analysis
from wunderunner.settings import get_settings
from wunderunner.workflows.state import Learning


def _get_client() -> docker.DockerClient:
    """Get Docker client from environment."""
    return docker.from_env()


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
    prompt = compose_agent.USER_PROMPT.render(
        analysis=analysis.model_dump(),
        dockerfile=dockerfile_content,
        learnings=learnings,
        hints=hints,
        existing_compose=existing,
    )

    deps = AgentDeps(project_dir=project_path) if project_path else None

    try:
        result = await compose_agent.agent.run(prompt, deps=deps)
        return result.output
    except Exception as e:
        raise ServicesError(f"Failed to generate docker-compose.yaml: {e}") from e


async def start(path: Path) -> list[str]:
    """Start services with docker compose up.

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

    # docker compose CLI is the standard way to orchestrate
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

    # Get container IDs via CLI (compose-specific)
    container_ids = await _get_compose_container_ids(path)
    if not container_ids:
        raise StartError("No containers started")

    return container_ids


async def _get_compose_container_ids(path: Path) -> list[str]:
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
    """Check health of running containers with HTTP probes.

    First waits for containers to be running, then probes exposed HTTP ports.

    Args:
        container_ids: List of container IDs to check.
        timeout: Maximum seconds to wait for healthy state.

    Raises:
        HealthcheckError: If healthcheck fails.
    """
    if not container_ids:
        raise HealthcheckError("No containers to check")

    client = _get_client()
    start_time = asyncio.get_event_loop().time()

    # Phase 1: Wait for containers to be running
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise HealthcheckError(f"Health check timed out after {timeout}s")

        all_running = True
        for container_id in container_ids:
            status = _get_container_status(client, container_id)

            if status == "exited":
                logs = _get_container_logs(client, container_id)
                raise HealthcheckError(f"Container {container_id[:12]} exited:\n{logs}")

            if status != "running":
                all_running = False

        if all_running:
            break

        await asyncio.sleep(1)

    # Phase 2: HTTP health probes for containers with exposed ports
    http_targets = _get_http_targets(client, container_ids)

    if not http_targets:
        return  # No HTTP ports to probe

    async with httpx.AsyncClient(timeout=5.0) as http_client:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise HealthcheckError(f"HTTP health check timed out after {timeout}s")

            all_healthy = True
            for url in http_targets:
                try:
                    response = await http_client.get(url)
                    if response.status_code >= 500:
                        all_healthy = False
                except httpx.RequestError:
                    all_healthy = False

            if all_healthy:
                return

            await asyncio.sleep(2)


def _get_http_targets(client: docker.DockerClient, container_ids: list[str]) -> list[str]:
    """Get HTTP URLs for containers with exposed ports.

    Returns URLs for localhost with the host port mapping.
    Only returns ports that look like HTTP (common web ports).
    """
    http_ports = {80, 443, 3000, 5000, 8000, 8080, 8888, 9000}
    targets = []

    for container_id in container_ids:
        ports = _get_container_ports(client, container_id)
        for host_port, container_port in ports:
            if container_port in http_ports:
                targets.append(f"http://localhost:{host_port}")

    return targets


def _get_container_ports(client: docker.DockerClient, container_id: str) -> list[tuple[int, int]]:
    """Get port mappings for a container as (host_port, container_port) tuples."""
    try:
        container = client.containers.get(container_id)
    except NotFound:
        return []

    ports = []
    port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {})

    for container_port_str, bindings in port_bindings.items():
        if not bindings:
            continue

        # container_port_str is like "8000/tcp"
        container_port = int(container_port_str.split("/")[0])

        for binding in bindings:
            host_port = binding.get("HostPort")
            if host_port:
                ports.append((int(host_port), container_port))

    return ports


def _get_container_status(client: docker.DockerClient, container_id: str) -> str:
    """Get the status of a container."""
    try:
        container = client.containers.get(container_id)
        return container.status
    except NotFound:
        return "not_found"


def _get_container_logs(client: docker.DockerClient, container_id: str, tail: int = 50) -> str:
    """Get recent logs from a container."""
    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=tail, stdout=True, stderr=True)
        if isinstance(logs, bytes):
            return logs.decode("utf-8", errors="replace")
        return str(logs)
    except NotFound:
        return "Container not found"

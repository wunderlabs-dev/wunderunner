"""Services (docker-compose) activities.

Uses docker-py SDK for container inspection and healthchecks.
Uses docker compose CLI for orchestration (no SDK support for compose).
"""

import asyncio
from pathlib import Path

import docker
import httpx
from docker.errors import NotFound

from wunderunner.activities.docker import get_client
from wunderunner.agents.generation import compose as compose_agent
from wunderunner.exceptions import HealthcheckError, ServicesError, StartError
from wunderunner.models.analysis import Analysis
from wunderunner.settings import Generation, get_fallback_model
from wunderunner.workflows.state import Learning


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
    # Extract secrets from analysis
    secrets = [v for v in analysis.env_vars if v.secret]

    prompt = compose_agent.USER_PROMPT.render(
        analysis=analysis.model_dump(),
        dockerfile=dockerfile_content,
        secrets=secrets,
        learnings=learnings,
        hints=hints,
        existing_compose=existing,
    )

    try:
        result = await compose_agent.agent.run(
            prompt,
            model=get_fallback_model(Generation.COMPOSE),
        )
        return result.output.compose_yaml
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
    compose_path = path / "docker-compose.yaml"

    if not compose_path.exists():
        raise StartError("docker-compose.yaml not found. Run generate first.")

    # First, stop and remove any existing containers/volumes to avoid mount conflicts
    # This cleans up corrupted volumes from previous failed attempts
    down_cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_path),
        "down",
        "-v",  # Remove volumes
        "--remove-orphans",
    ]

    down_process = await asyncio.create_subprocess_exec(
        *down_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(path),
    )
    await down_process.communicate()  # Ignore errors - may not exist yet

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
    compose_path = path / "docker-compose.yaml"

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
    compose_path = path / "docker-compose.yaml"

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

    client = get_client()
    start_time = asyncio.get_event_loop().time()

    await _wait_for_containers_running(client, container_ids, start_time, timeout)
    await _wait_for_http_healthy(client, container_ids, start_time, timeout)


async def _wait_for_containers_running(
    client: docker.DockerClient,
    container_ids: list[str],
    start_time: float,
    timeout: int,
) -> None:
    """Wait for all containers to reach running state."""
    while True:
        _check_timeout(client, container_ids, start_time, timeout, "waiting for containers")

        failed_id = _find_exited_container(client, container_ids)
        if failed_id:
            logs = _get_container_logs(client, failed_id)
            raise HealthcheckError(f"Container {failed_id[:12]} exited:\n{logs}")

        if _all_containers_running(client, container_ids):
            return

        await asyncio.sleep(1)


async def _wait_for_http_healthy(
    client: docker.DockerClient,
    container_ids: list[str],
    start_time: float,
    timeout: int,
) -> None:
    """Wait for HTTP endpoints to respond successfully."""
    http_targets = _get_http_targets(client, container_ids)
    if not http_targets:
        return

    async with httpx.AsyncClient(timeout=5.0) as http_client:
        while True:
            _check_timeout(client, container_ids, start_time, timeout, "HTTP health check")

            error = await _probe_http_targets(http_client, http_targets)
            if error:
                all_logs = _get_all_container_logs(client, container_ids)
                raise HealthcheckError(f"{error}\n\n{all_logs}")

            if await _all_targets_healthy(http_client, http_targets):
                return

            await asyncio.sleep(2)


def _check_timeout(
    client: docker.DockerClient,
    container_ids: list[str],
    start_time: float,
    timeout: int,
    phase: str,
) -> None:
    """Raise HealthcheckError if timeout exceeded."""
    elapsed = asyncio.get_event_loop().time() - start_time
    if elapsed > timeout:
        all_logs = _get_all_container_logs(client, container_ids)
        raise HealthcheckError(f"Health check timed out after {timeout}s ({phase})\n\n{all_logs}")


def _find_exited_container(client: docker.DockerClient, container_ids: list[str]) -> str | None:
    """Return first exited container ID, or None if none exited."""
    for container_id in container_ids:
        if _get_container_status(client, container_id) == "exited":
            return container_id
    return None


def _all_containers_running(client: docker.DockerClient, container_ids: list[str]) -> bool:
    """Check if all containers are in running state."""
    return all(_get_container_status(client, cid) == "running" for cid in container_ids)


async def _probe_http_targets(
    http_client: httpx.AsyncClient,
    targets: list[str],
) -> str | None:
    """Probe targets for server errors. Returns error message or None."""
    for url in targets:
        try:
            response = await http_client.get(url)
            if response.status_code >= 500:
                return f"HTTP {response.status_code} from {url}"
        except httpx.RequestError:
            pass  # Not ready yet, not a fatal error
    return None


async def _all_targets_healthy(http_client: httpx.AsyncClient, targets: list[str]) -> bool:
    """Check if all HTTP targets respond without error."""
    for url in targets:
        try:
            response = await http_client.get(url)
            if response.status_code >= 500:
                return False
        except httpx.RequestError:
            return False
    return True


def _get_http_targets(client: docker.DockerClient, container_ids: list[str]) -> list[str]:
    """Get HTTP URLs for containers with exposed ports.

    Returns URLs for localhost with the host port mapping.
    Probes all exposed TCP ports - the healthcheck handles non-HTTP gracefully.
    """
    targets = []

    for container_id in container_ids:
        ports = _get_container_ports(client, container_id)
        for host_port, _container_port in ports:
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


def _get_all_container_logs(client: docker.DockerClient, container_ids: list[str]) -> str:
    """Get logs from all containers, formatted with container names."""
    parts = []
    for container_id in container_ids:
        try:
            container = client.containers.get(container_id)
            name = container.name
        except NotFound:
            name = container_id[:12]

        logs = _get_container_logs(client, container_id)
        parts.append(f"=== {name} ===\n{logs}")

    return "\n\n".join(parts)

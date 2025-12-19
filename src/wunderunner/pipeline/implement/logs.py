"""Capture and save verification logs."""

from pathlib import Path

import aiofiles

from wunderunner.settings import get_settings


def get_log_path(project_dir: Path, attempt: int) -> Path:
    """Get path to log file for an attempt.

    Args:
        project_dir: Project root directory.
        attempt: Attempt number.

    Returns:
        Path to log file.
    """
    settings = get_settings()
    return project_dir / settings.cache_dir / "logs" / f"attempt-{attempt}.log"


async def save_logs(
    project_dir: Path,
    attempt: int,
    stdout: str | None,
    stderr: str | None,
    command: str | None = None,
) -> Path:
    """Save verification output to log file.

    Args:
        project_dir: Project root directory.
        attempt: Attempt number.
        stdout: Standard output content.
        stderr: Standard error content.
        command: Command that was run (optional).

    Returns:
        Path to created log file.
    """
    log_path = get_log_path(project_dir, attempt)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    content_parts = []

    if command:
        content_parts.append(f"Command: {command}\n")
        content_parts.append("=" * 50 + "\n\n")

    if stdout:
        content_parts.append("=== STDOUT ===\n")
        content_parts.append(stdout)
        content_parts.append("\n\n")

    if stderr:
        content_parts.append("=== STDERR ===\n")
        content_parts.append(stderr)
        content_parts.append("\n")

    async with aiofiles.open(log_path, "w") as f:
        await f.write("".join(content_parts))

    return log_path

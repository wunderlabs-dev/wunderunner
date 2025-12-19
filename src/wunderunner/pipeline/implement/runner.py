"""IMPLEMENT phase runner.

Reads plan.md, writes files, runs verification.
"""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.artifacts import get_artifact_path
from wunderunner.pipeline.implement.logs import save_logs
from wunderunner.pipeline.implement.parser import parse_plan
from wunderunner.pipeline.implement.verify import run_verification
from wunderunner.pipeline.implement.writer import write_files
from wunderunner.pipeline.models import ImplementResult


async def run_implement(project_dir: Path, attempt: int = 1) -> ImplementResult:
    """Execute IMPLEMENT phase.

    Reads plan.md, writes files to project directory, runs verification steps.

    Args:
        project_dir: Project root directory.
        attempt: Current attempt number (for log naming).

    Returns:
        ImplementResult with success status and error details if failed.

    Raises:
        FileNotFoundError: If plan.md doesn't exist.
    """
    # Read plan artifact
    plan_path = get_artifact_path(project_dir, "plan.md")
    async with aiofiles.open(plan_path) as f:
        plan_content = await f.read()

    # Parse plan
    parsed = parse_plan(plan_content)

    if not parsed.dockerfile:
        return ImplementResult(
            success=False,
            error="No Dockerfile found in plan.md",
        )

    # Write files
    files_written = await write_files(project_dir, parsed)

    # Run verification
    verify_result = await run_verification(project_dir, parsed.verification_steps)

    if verify_result.success:
        return ImplementResult(
            success=True,
            files_written=files_written,
        )

    # Save logs on failure
    log_path = await save_logs(
        project_dir=project_dir,
        attempt=attempt,
        stdout=verify_result.stdout,
        stderr=verify_result.stderr,
        command=verify_result.failed_step,
    )

    return ImplementResult(
        success=False,
        files_written=files_written,
        phase=verify_result.phase,
        error=verify_result.error,
        logs=str(log_path),
    )

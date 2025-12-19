"""Run verification commands and capture results."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from wunderunner.pipeline.implement.parser import VerificationStep


@dataclass
class VerificationResult:
    """Result of running verification steps."""

    success: bool
    failed_step: str | None = None
    phase: str | None = None
    error: str | None = None
    stdout: str | None = None
    stderr: str | None = None


async def run_verification(
    project_dir: Path,
    steps: list[VerificationStep],
) -> VerificationResult:
    """Execute verification steps sequentially.

    Stops on first failure and returns error details.

    Args:
        project_dir: Directory to run commands in.
        steps: List of verification steps from plan.

    Returns:
        VerificationResult with success status and error details if failed.
    """
    for step in steps:
        result = await _run_step(project_dir, step)
        if not result.success:
            return result

    return VerificationResult(success=True)


async def _run_step(project_dir: Path, step: VerificationStep) -> VerificationResult:
    """Run a single verification step.

    Args:
        project_dir: Directory to run command in.
        step: Verification step with command and expected outcome.

    Returns:
        VerificationResult for this step.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            step.command,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # returncode is always set after communicate()
        returncode = process.returncode
        assert returncode is not None, "Process must have returncode after communicate()"

        # Check if step passed based on expected outcome
        passed = _check_expected(step.expected, returncode, stdout_str, stderr_str)

        if passed:
            return VerificationResult(
                success=True,
                stdout=stdout_str,
                stderr=stderr_str,
            )
        else:
            return VerificationResult(
                success=False,
                failed_step=step.command,
                phase=_infer_phase(step.command),
                error=stderr_str or stdout_str or f"Command exited with code {returncode}",
                stdout=stdout_str,
                stderr=stderr_str,
            )

    except Exception as e:
        return VerificationResult(
            success=False,
            failed_step=step.command,
            error=str(e),
        )


def _check_expected(expected: str, returncode: int, stdout: str, stderr: str) -> bool:
    """Check if command output matches expected outcome.

    Args:
        expected: Expected outcome string (e.g., "exit 0", "200 OK").
        returncode: Process return code.
        stdout: Standard output.
        stderr: Standard error.

    Returns:
        True if outcome matches expected.
    """
    expected_lower = expected.lower()

    # Check for exit code expectations
    if "exit 0" in expected_lower:
        return returncode == 0
    if "exit" in expected_lower:
        # Generic exit check - non-zero is failure
        return returncode == 0

    # Check for content in output
    if "200" in expected or "ok" in expected_lower:
        return "200" in stdout or "ok" in stdout.lower()

    # Check for container/service expectations
    if "start" in expected_lower or "running" in expected_lower:
        return returncode == 0

    # Default: success if exit code is 0
    return returncode == 0


def _infer_phase(command: str) -> str:
    """Infer the phase from the command.

    Args:
        command: The verification command.

    Returns:
        Phase name: BUILD, START, or HEALTHCHECK.
    """
    command_lower = command.lower()

    if "build" in command_lower:
        return "BUILD"
    if "up" in command_lower or "run" in command_lower:
        return "START"
    if "curl" in command_lower or "wget" in command_lower or "health" in command_lower:
        return "HEALTHCHECK"

    return "BUILD"

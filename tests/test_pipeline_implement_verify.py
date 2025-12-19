"""Tests for verification runner."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.pipeline.implement.parser import VerificationStep
from wunderunner.pipeline.implement.verify import (
    VerificationResult,
    run_verification,
)


@pytest.mark.asyncio
async def test_run_verification_success(tmp_path: Path):
    """run_verification returns success when all steps pass."""
    steps = [
        VerificationStep(command="echo hello", expected="exit 0"),
    ]

    # Mock subprocess to return success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "hello\n"
    mock_process.stderr = ""

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process
        mock_process.communicate = AsyncMock(return_value=(b"hello\n", b""))

        result = await run_verification(tmp_path, steps)

    assert isinstance(result, VerificationResult)
    assert result.success is True
    assert result.failed_step is None


@pytest.mark.asyncio
async def test_run_verification_failure(tmp_path: Path):
    """run_verification returns failure with details on error."""
    steps = [
        VerificationStep(command="docker build .", expected="exit 0"),
    ]

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Error: Dockerfile not found"))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_verification(tmp_path, steps)

    assert result.success is False
    assert result.failed_step == "docker build ."
    assert "Dockerfile not found" in result.error


@pytest.mark.asyncio
async def test_run_verification_stops_on_first_failure(tmp_path: Path):
    """run_verification stops after first failed step."""
    steps = [
        VerificationStep(command="step1", expected="exit 0"),
        VerificationStep(command="step2", expected="exit 0"),
    ]

    call_count = 0

    async def mock_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        process.returncode = 1  # Always fail
        process.communicate = AsyncMock(return_value=(b"", b"error"))
        return process

    with patch("asyncio.create_subprocess_shell", side_effect=mock_subprocess):
        result = await run_verification(tmp_path, steps)

    assert result.success is False
    assert call_count == 1  # Only first step ran

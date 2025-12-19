"""Tests for IMPLEMENT phase runner."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.pipeline.implement.runner import run_implement
from wunderunner.pipeline.models import ImplementResult


@pytest.fixture
def project_with_plan(tmp_path: Path) -> Path:
    """Create project with plan.md artifact."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "plan.md").write_text("""# Containerization Plan

## Summary
Python app

## Files

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
```

## Verification
1. `docker build -t app .` → exit 0
""")
    return tmp_path


@pytest.mark.asyncio
async def test_run_implement_writes_files(project_with_plan: Path):
    """run_implement writes Dockerfile from plan."""
    # Mock verification to succeed
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        await run_implement(project_with_plan, attempt=1)

    assert (project_with_plan / "Dockerfile").exists()
    assert "FROM python:3.11-slim" in (project_with_plan / "Dockerfile").read_text()


@pytest.mark.asyncio
async def test_run_implement_returns_success(project_with_plan: Path):
    """run_implement returns success when verification passes."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"Built!", b""))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_implement(project_with_plan, attempt=1)

    assert isinstance(result, ImplementResult)
    assert result.success is True
    assert "Dockerfile" in result.files_written


@pytest.mark.asyncio
async def test_run_implement_returns_failure_with_logs(project_with_plan: Path):
    """run_implement returns failure with log path on error."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Build failed"))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_implement(project_with_plan, attempt=2)

    assert result.success is False
    assert result.phase == "BUILD"
    assert "Build failed" in result.error
    assert result.logs is not None
    assert "attempt-2.log" in result.logs

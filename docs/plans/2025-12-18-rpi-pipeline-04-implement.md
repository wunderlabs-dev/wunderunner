## Part 4: Implement Phase

The IMPLEMENT phase reads `plan.md`, writes files, and runs verification. Mostly code, minimal LLM.

---

### Task 4.1: Create implement module structure

**Files:**
- Create: `src/wunderunner/pipeline/implement/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/implement
```

```python
# src/wunderunner/pipeline/implement/__init__.py
"""IMPLEMENT phase - write files and run verification."""

from wunderunner.pipeline.implement.runner import run_implement

__all__ = ["run_implement"]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/implement/
git commit -m "feat(pipeline): add implement phase module structure"
```

---

### Task 4.2: Add plan parser

**Files:**
- Create: `src/wunderunner/pipeline/implement/parser.py`
- Test: `tests/test_pipeline_implement_parser.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_parser.py
"""Tests for plan.md parser."""

import pytest
from wunderunner.pipeline.implement.parser import parse_plan, ParsedPlan


def test_parse_plan_extracts_dockerfile():
    """parse_plan extracts Dockerfile content from code block."""
    plan_md = """# Containerization Plan

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

## Reasoning
Simple setup
"""
    result = parse_plan(plan_md)

    assert isinstance(result, ParsedPlan)
    assert result.dockerfile is not None
    assert "FROM python:3.11-slim" in result.dockerfile
    assert result.compose is None


def test_parse_plan_extracts_compose():
    """parse_plan extracts docker-compose.yaml content."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
```

### docker-compose.yaml
```yaml
services:
  app:
    build: .
    ports:
      - "3000:3000"
```

## Verification
1. `docker compose build` → exit 0
"""
    result = parse_plan(plan_md)

    assert result.dockerfile is not None
    assert result.compose is not None
    assert "services:" in result.compose
    assert "build: ." in result.compose


def test_parse_plan_extracts_verification():
    """parse_plan extracts verification steps."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM python:3.11
```

## Verification
1. `docker build -t app .` → exit 0
2. `docker run -d -p 8000:8000 app` → container starts
3. `curl localhost:8000/health` → 200 OK
"""
    result = parse_plan(plan_md)

    assert len(result.verification_steps) == 3
    assert result.verification_steps[0].command == "docker build -t app ."
    assert result.verification_steps[0].expected == "exit 0"


def test_parse_plan_handles_missing_sections():
    """parse_plan handles minimal plan."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM alpine
```
"""
    result = parse_plan(plan_md)

    assert result.dockerfile == "FROM alpine"
    assert result.compose is None
    assert result.verification_steps == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_parser.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan parser**

```python
# src/wunderunner/pipeline/implement/parser.py
"""Parse plan.md artifact to extract file contents and verification steps."""

import re
from dataclasses import dataclass


@dataclass
class VerificationStep:
    """A verification step extracted from plan."""

    command: str
    expected: str


@dataclass
class ParsedPlan:
    """Parsed contents of plan.md."""

    dockerfile: str | None
    compose: str | None
    verification_steps: list[VerificationStep]


def parse_plan(plan_content: str) -> ParsedPlan:
    """Parse plan.md content to extract file contents.

    Extracts:
    - Dockerfile content from ```dockerfile code block
    - docker-compose.yaml content from ```yaml code block
    - Verification steps from numbered list

    Args:
        plan_content: Raw markdown content of plan.md.

    Returns:
        ParsedPlan with extracted contents.
    """
    dockerfile = _extract_code_block(plan_content, "dockerfile")
    compose = _extract_code_block(plan_content, "yaml")
    verification = _extract_verification_steps(plan_content)

    return ParsedPlan(
        dockerfile=dockerfile,
        compose=compose,
        verification_steps=verification,
    )


def _extract_code_block(content: str, language: str) -> str | None:
    """Extract content from a fenced code block.

    Args:
        content: Markdown content.
        language: Code block language (dockerfile, yaml).

    Returns:
        Code block content without fences, or None if not found.
    """
    # Match ```language ... ``` blocks
    pattern = rf"```{language}\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def _extract_verification_steps(content: str) -> list[VerificationStep]:
    """Extract verification steps from numbered list.

    Expected format:
    1. `command` → expected
    2. `command` → expected

    Args:
        content: Markdown content.

    Returns:
        List of VerificationStep objects.
    """
    steps = []

    # Find the Verification section
    verification_match = re.search(r"## Verification\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not verification_match:
        return steps

    verification_section = verification_match.group(1)

    # Match numbered items: 1. `command` → expected
    pattern = r"\d+\.\s+`([^`]+)`\s+→\s+(.+)"
    for match in re.finditer(pattern, verification_section):
        command = match.group(1).strip()
        expected = match.group(2).strip()
        steps.append(VerificationStep(command=command, expected=expected))

    return steps
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/parser.py tests/test_pipeline_implement_parser.py
git commit -m "feat(pipeline): add plan.md parser"
```

---

### Task 4.3: Add file writer

**Files:**
- Create: `src/wunderunner/pipeline/implement/writer.py`
- Test: `tests/test_pipeline_implement_writer.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_writer.py
"""Tests for file writer."""

import pytest
from pathlib import Path

from wunderunner.pipeline.implement.writer import write_files
from wunderunner.pipeline.implement.parser import ParsedPlan, VerificationStep


@pytest.mark.asyncio
async def test_write_files_creates_dockerfile(tmp_path: Path):
    """write_files creates Dockerfile in project directory."""
    plan = ParsedPlan(
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    dockerfile_path = tmp_path / "Dockerfile"
    assert dockerfile_path.exists()
    assert "FROM python:3.11-slim" in dockerfile_path.read_text()


@pytest.mark.asyncio
async def test_write_files_creates_compose(tmp_path: Path):
    """write_files creates docker-compose.yaml."""
    plan = ParsedPlan(
        dockerfile="FROM node:20\n",
        compose="services:\n  app:\n    build: .\n",
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" in files
    compose_path = tmp_path / "docker-compose.yaml"
    assert compose_path.exists()
    assert "services:" in compose_path.read_text()


@pytest.mark.asyncio
async def test_write_files_skips_none_values(tmp_path: Path):
    """write_files skips files with None content."""
    plan = ParsedPlan(
        dockerfile="FROM alpine\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" not in files
    assert not (tmp_path / "docker-compose.yaml").exists()


@pytest.mark.asyncio
async def test_write_files_overwrites_existing(tmp_path: Path):
    """write_files overwrites existing files."""
    # Create existing Dockerfile
    (tmp_path / "Dockerfile").write_text("FROM old:version\n")

    plan = ParsedPlan(
        dockerfile="FROM new:version\n",
        compose=None,
        verification_steps=[],
    )

    await write_files(tmp_path, plan)

    assert "FROM new:version" in (tmp_path / "Dockerfile").read_text()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_writer.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write file writer**

```python
# src/wunderunner/pipeline/implement/writer.py
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/writer.py tests/test_pipeline_implement_writer.py
git commit -m "feat(pipeline): add file writer"
```

---

### Task 4.4: Add verification runner

**Files:**
- Create: `src/wunderunner/pipeline/implement/verify.py`
- Test: `tests/test_pipeline_implement_verify.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_verify.py
"""Tests for verification runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.implement.verify import (
    run_verification,
    VerificationResult,
)
from wunderunner.pipeline.implement.parser import VerificationStep


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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_verify.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write verification runner**

```python
# src/wunderunner/pipeline/implement/verify.py
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

        # Check if step passed based on expected outcome
        passed = _check_expected(step.expected, process.returncode, stdout_str, stderr_str)

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
                error=stderr_str or stdout_str or f"Command exited with code {process.returncode}",
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_verify.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/verify.py tests/test_pipeline_implement_verify.py
git commit -m "feat(pipeline): add verification runner"
```

---

### Task 4.5: Add log capture

**Files:**
- Create: `src/wunderunner/pipeline/implement/logs.py`
- Test: `tests/test_pipeline_implement_logs.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_logs.py
"""Tests for log capture."""

import pytest
from pathlib import Path

from wunderunner.pipeline.implement.logs import save_logs, get_log_path


@pytest.mark.asyncio
async def test_save_logs_creates_file(tmp_path: Path):
    """save_logs creates log file in .wunderunner/logs/."""
    path = await save_logs(
        project_dir=tmp_path,
        attempt=1,
        stdout="Build output",
        stderr="Error message",
    )

    assert path.exists()
    assert ".wunderunner/logs/attempt-1.log" in str(path)

    content = path.read_text()
    assert "Build output" in content
    assert "Error message" in content


def test_get_log_path(tmp_path: Path):
    """get_log_path returns correct path."""
    path = get_log_path(tmp_path, 3)
    assert path == tmp_path / ".wunderunner" / "logs" / "attempt-3.log"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_logs.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write log capture**

```python
# src/wunderunner/pipeline/implement/logs.py
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_logs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/logs.py tests/test_pipeline_implement_logs.py
git commit -m "feat(pipeline): add log capture"
```

---

### Task 4.6: Add implement phase runner

**Files:**
- Create: `src/wunderunner/pipeline/implement/runner.py`
- Test: `tests/test_pipeline_implement_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_runner.py
"""Tests for IMPLEMENT phase runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.models import ImplementResult
from wunderunner.pipeline.implement.runner import run_implement


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

        result = await run_implement(project_with_plan, attempt=1)

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implement phase runner**

```python
# src/wunderunner/pipeline/implement/runner.py
"""IMPLEMENT phase runner.

Reads plan.md, writes files, runs verification.
"""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.artifacts import get_artifact_path
from wunderunner.pipeline.models import ImplementResult
from wunderunner.pipeline.implement.parser import parse_plan
from wunderunner.pipeline.implement.writer import write_files
from wunderunner.pipeline.implement.verify import run_verification
from wunderunner.pipeline.implement.logs import save_logs


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
```

**Step 4: Update __init__.py**

```python
# src/wunderunner/pipeline/implement/__init__.py
"""IMPLEMENT phase - write files and run verification."""

from wunderunner.pipeline.implement.runner import run_implement

__all__ = ["run_implement"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/implement/ tests/test_pipeline_implement_runner.py
git commit -m "feat(pipeline): add IMPLEMENT phase runner"
```

---

**Part 4 Complete.** IMPLEMENT phase with parser, writer, verification, and log capture. Next: Part 5 (Error Handling).

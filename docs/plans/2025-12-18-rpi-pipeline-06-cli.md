## Part 6: CLI Integration

Wire up the pipeline to the CLI with feature flag and caching.

---

### Task 6.1: Add pipeline runner

**Files:**
- Create: `src/wunderunner/pipeline/runner.py`
- Test: `tests/test_pipeline_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_runner.py
"""Tests for main pipeline runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.runner import run_pipeline, PipelineResult, PipelineStatus
from wunderunner.pipeline.models import (
    ResearchResult,
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
    ContainerizationPlan,
    ImplementResult,
)


@pytest.fixture
def mock_research_result() -> ResearchResult:
    """Mock research result."""
    return ResearchResult(
        runtime=RuntimeFindings(language="python", version="3.11"),
        dependencies=DependencyFindings(package_manager="pip"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )


@pytest.fixture
def mock_plan() -> ContainerizationPlan:
    """Mock plan."""
    return ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11\n",
        verification=[],
        reasoning="Simple",
        constraints_honored=[],
    )


@pytest.mark.asyncio
async def test_run_pipeline_success(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline returns success on happy path."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock) as mock_r:
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock) as mock_p:
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_r.return_value = mock_research_result
                mock_p.return_value = mock_plan
                mock_i.return_value = ImplementResult(success=True, files_written=["Dockerfile"])

                result = await run_pipeline(tmp_path)

    assert isinstance(result, PipelineResult)
    assert result.status == PipelineStatus.SUCCESS
    assert "Dockerfile" in result.files_written


@pytest.mark.asyncio
async def test_run_pipeline_retries_on_failure(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline retries when implement fails."""
    # First implement fails, second succeeds
    impl_results = [
        ImplementResult(success=False, phase="BUILD", error="Failed"),
        ImplementResult(success=True, files_written=["Dockerfile"]),
    ]
    impl_call_count = 0

    async def mock_implement(*args, **kwargs):
        nonlocal impl_call_count
        result = impl_results[impl_call_count]
        impl_call_count += 1
        return result

    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", side_effect=mock_implement):
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    with patch("wunderunner.pipeline.runner.run_fix_plan", new_callable=AsyncMock) as mock_fp:
                        from wunderunner.pipeline.models import ErrorAnalysis, FixPlan
                        mock_er.return_value = ErrorAnalysis(
                            error_summary="e", root_cause="r",
                            fix_history_review="f", recommendation="continue",
                        )
                        mock_fp.return_value = FixPlan(
                            summary="s", dockerfile="FROM x\n",
                            changes_description="c", constraints_honored=[],
                        )

                        result = await run_pipeline(tmp_path, max_attempts=3)

    assert result.status == PipelineStatus.SUCCESS
    assert impl_call_count == 2


@pytest.mark.asyncio
async def test_run_pipeline_stops_on_max_attempts(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline stops after max_attempts."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=False, phase="BUILD", error="Fail")
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    with patch("wunderunner.pipeline.runner.run_fix_plan", new_callable=AsyncMock) as mock_fp:
                        from wunderunner.pipeline.models import ErrorAnalysis, FixPlan
                        mock_er.return_value = ErrorAnalysis(
                            error_summary="e", root_cause="r",
                            fix_history_review="f", recommendation="continue",
                        )
                        mock_fp.return_value = FixPlan(
                            summary="s", dockerfile="FROM x\n",
                            changes_description="c", constraints_honored=[],
                        )

                        result = await run_pipeline(tmp_path, max_attempts=2)

    assert result.status == PipelineStatus.MAX_ATTEMPTS
    assert result.error is not None


@pytest.mark.asyncio
async def test_run_pipeline_stops_on_exhaustion(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline stops when error research says stop."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=False, phase="BUILD", error="Fail")
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    from wunderunner.pipeline.models import ErrorAnalysis
                    mock_er.return_value = ErrorAnalysis(
                        error_summary="e", root_cause="r",
                        fix_history_review="f", recommendation="stop",  # Says stop!
                    )

                    result = await run_pipeline(tmp_path, max_attempts=5)

    assert result.status == PipelineStatus.EXHAUSTED
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write pipeline runner**

```python
# src/wunderunner/pipeline/runner.py
"""Main pipeline runner - orchestrates RESEARCH → PLAN → IMPLEMENT cycle."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from wunderunner.pipeline.artifacts import (
    write_research,
    read_research,
    write_plan,
    read_plan,
    write_fix_history,
    read_fix_history,
    write_error_analysis,
    write_fix_plan,
    get_artifact_path,
)
from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    FixError,
    ImplementResult,
)
from wunderunner.pipeline.research import run_research
from wunderunner.pipeline.plan import run_plan
from wunderunner.pipeline.implement import run_implement
from wunderunner.pipeline.errors import (
    run_error_research,
    run_fix_plan,
    update_constraints,
    increment_success_counts,
    derive_constraint,
)


class PipelineStatus(str, Enum):
    """Final status of pipeline run."""

    SUCCESS = "success"
    MAX_ATTEMPTS = "max_attempts"
    EXHAUSTED = "exhausted"
    ERROR = "error"


@dataclass
class PipelineResult:
    """Result of pipeline run."""

    status: PipelineStatus
    files_written: list[str]
    attempts: int
    error: str | None = None


ProgressCallback = Callable[[str, str], None]


async def run_pipeline(
    project_dir: Path,
    max_attempts: int = 5,
    rebuild: bool = False,
    replan: bool = False,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the RESEARCH → PLAN → IMPLEMENT pipeline.

    Args:
        project_dir: Project root directory.
        max_attempts: Maximum fix attempts before giving up.
        rebuild: Force re-run RESEARCH phase.
        replan: Force re-run PLAN phase.
        on_progress: Optional callback for progress updates.

    Returns:
        PipelineResult with final status.
    """

    def progress(phase: str, message: str) -> None:
        if on_progress:
            on_progress(phase, message)

    try:
        # Initialize or load fix history
        fix_history = await read_fix_history(project_dir)
        if not fix_history:
            fix_history = FixHistory(project=project_dir.name)

        # RESEARCH phase
        research_path = get_artifact_path(project_dir, "research.md")
        if rebuild or not research_path.exists():
            progress("RESEARCH", "Running project analysis...")
            research_result = await run_research(project_dir)
            await write_research(project_dir, research_result)
            progress("RESEARCH", "Complete")

        # PLAN phase
        plan_path = get_artifact_path(project_dir, "plan.md")
        if rebuild or replan or not plan_path.exists():
            progress("PLAN", "Generating containerization plan...")
            await run_plan(project_dir)
            progress("PLAN", "Complete")

        # IMPLEMENT phase with retry loop
        attempt = 0
        last_error: str | None = None
        files_written: list[str] = []

        while attempt < max_attempts:
            attempt += 1
            progress("IMPLEMENT", f"Attempt {attempt}/{max_attempts}")

            impl_result = await run_implement(project_dir, attempt=attempt)

            if impl_result.success:
                # Success! Update constraints and return
                fix_history = increment_success_counts(fix_history)
                await write_fix_history(project_dir, fix_history)

                progress("IMPLEMENT", "Success!")
                return PipelineResult(
                    status=PipelineStatus.SUCCESS,
                    files_written=impl_result.files_written,
                    attempts=attempt,
                )

            # Failed - run error handling cycle
            last_error = impl_result.error
            files_written = impl_result.files_written

            progress("ERROR-RESEARCH", "Analyzing error...")
            research_content = await read_research(project_dir)
            plan_content = await read_plan(project_dir)

            error_context = {
                "phase": impl_result.phase,
                "error": impl_result.error,
                "log_path": impl_result.logs,
            }

            error_analysis = await run_error_research(
                project_dir=project_dir,
                error_context=error_context,
                research_content=research_content,
                fix_history=fix_history,
            )
            await write_error_analysis(project_dir, error_analysis, attempt)

            # Check if we should stop
            if error_analysis.recommendation == "stop":
                progress("ERROR-RESEARCH", "All approaches exhausted")
                return PipelineResult(
                    status=PipelineStatus.EXHAUSTED,
                    files_written=files_written,
                    attempts=attempt,
                    error=last_error,
                )

            # Generate fix plan
            progress("FIX-PLAN", "Generating fix...")
            constraints = [
                c.rule for c in fix_history.active_constraints
                if c.status.value == "hard"
            ]

            fix_plan = await run_fix_plan(
                project_dir=project_dir,
                error_analysis=error_analysis,
                current_plan=plan_content,
                constraints=constraints,
            )
            await write_fix_plan(project_dir, fix_plan)

            # Record attempt
            fix_attempt = FixAttempt(
                attempt=attempt,
                phase=impl_result.phase or "UNKNOWN",
                error=FixError(
                    type=impl_result.phase or "unknown",
                    message=impl_result.error or "Unknown error",
                ),
                diagnosis=error_analysis.root_cause,
                outcome="failure",
            )
            fix_history.attempts.append(fix_attempt)

            # Update plan.md with fix plan content
            from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep
            updated_plan = ContainerizationPlan(
                summary=fix_plan.summary,
                dockerfile=fix_plan.dockerfile,
                compose=fix_plan.compose,
                verification=[],  # Keep original verification
                reasoning=fix_plan.changes_description,
                constraints_honored=fix_plan.constraints_honored,
            )
            await write_plan(project_dir, updated_plan)
            await write_fix_history(project_dir, fix_history)

            progress("FIX-PLAN", "Fix generated, retrying...")

        # Exceeded max attempts
        return PipelineResult(
            status=PipelineStatus.MAX_ATTEMPTS,
            files_written=files_written,
            attempts=attempt,
            error=last_error,
        )

    except Exception as e:
        return PipelineResult(
            status=PipelineStatus.ERROR,
            files_written=[],
            attempts=0,
            error=str(e),
        )
```

**Step 4: Update pipeline __init__.py**

```python
# src/wunderunner/pipeline/__init__.py
"""RESEARCH-PLAN-IMPLEMENT pipeline module."""

from wunderunner.pipeline.runner import run_pipeline, PipelineResult, PipelineStatus

__all__ = ["run_pipeline", "PipelineResult", "PipelineStatus"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/runner.py src/wunderunner/pipeline/__init__.py tests/test_pipeline_runner.py
git commit -m "feat(pipeline): add main pipeline runner"
```

---

### Task 6.2: Add CLI command

**Files:**
- Modify: `src/wunderunner/cli/main.py`
- Test: `tests/test_cli_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_pipeline.py
"""Tests for pipeline CLI command."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner

from wunderunner.cli.main import app
from wunderunner.pipeline.runner import PipelineResult, PipelineStatus


runner = CliRunner()


def test_containerize_v2_help():
    """containerize-v2 command shows help."""
    result = runner.invoke(app, ["containerize-v2", "--help"])
    assert result.exit_code == 0
    assert "RESEARCH" in result.stdout or "research" in result.stdout.lower()


def test_containerize_v2_requires_path():
    """containerize-v2 requires path argument."""
    result = runner.invoke(app, ["containerize-v2"])
    assert result.exit_code != 0


def test_containerize_v2_success(tmp_path: Path):
    """containerize-v2 reports success."""
    mock_result = PipelineResult(
        status=PipelineStatus.SUCCESS,
        files_written=["Dockerfile", "docker-compose.yaml"],
        attempts=1,
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = runner.invoke(app, ["containerize-v2", str(tmp_path)])

    assert result.exit_code == 0
    assert "Success" in result.stdout or "success" in result.stdout.lower()


def test_containerize_v2_failure(tmp_path: Path):
    """containerize-v2 reports failure."""
    mock_result = PipelineResult(
        status=PipelineStatus.MAX_ATTEMPTS,
        files_written=["Dockerfile"],
        attempts=5,
        error="Build failed",
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = runner.invoke(app, ["containerize-v2", str(tmp_path)])

    assert result.exit_code == 1
    assert "failed" in result.stdout.lower() or "error" in result.stdout.lower()


def test_containerize_v2_rebuild_flag(tmp_path: Path):
    """containerize-v2 --rebuild forces research."""
    mock_result = PipelineResult(
        status=PipelineStatus.SUCCESS,
        files_written=["Dockerfile"],
        attempts=1,
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_run:
        result = runner.invoke(app, ["containerize-v2", str(tmp_path), "--rebuild"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("rebuild") is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_pipeline.py -v`
Expected: FAIL (command doesn't exist yet)

**Step 3: Add CLI command**

```python
# src/wunderunner/cli/main.py (add new command)

# Add import at top
from wunderunner.pipeline import run_pipeline, PipelineResult, PipelineStatus

# Add command after existing commands

@app.command("containerize-v2")
def containerize_v2(
    path: Annotated[
        Path,
        typer.Argument(help="Path to project directory"),
    ],
    rebuild: Annotated[
        bool,
        typer.Option("--rebuild", help="Force re-run RESEARCH phase"),
    ] = False,
    replan: Annotated[
        bool,
        typer.Option("--replan", help="Force re-run PLAN phase"),
    ] = False,
    max_attempts: Annotated[
        int,
        typer.Option("--max-attempts", help="Maximum fix attempts"),
    ] = 5,
) -> None:
    """Containerize a project using RESEARCH → PLAN → IMPLEMENT pipeline.

    This is the v2 pipeline with file-based artifacts and fresh context per phase.
    """
    import asyncio
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {path}[/red]")
        raise typer.Exit(1)

    def on_progress(phase: str, message: str) -> None:
        console.print(f"[cyan]{phase}[/cyan]: {message}")

    console.print(Panel(f"[bold]Containerizing[/bold] {path.name}", expand=False))

    result: PipelineResult = asyncio.run(
        run_pipeline(
            project_dir=path,
            max_attempts=max_attempts,
            rebuild=rebuild,
            replan=replan,
            on_progress=on_progress,
        )
    )

    if result.status == PipelineStatus.SUCCESS:
        console.print()
        console.print(Panel(
            f"[green]Success![/green]\n"
            f"Files: {', '.join(result.files_written)}\n"
            f"Attempts: {result.attempts}",
            title="Pipeline Complete",
            expand=False,
        ))
    else:
        console.print()
        console.print(Panel(
            f"[red]Failed[/red]: {result.status.value}\n"
            f"Error: {result.error}\n"
            f"Attempts: {result.attempts}",
            title="Pipeline Failed",
            expand=False,
        ))
        raise typer.Exit(1)
```

**Step 4: Add import for Annotated if needed**

```python
# At top of src/wunderunner/cli/main.py, ensure these imports exist:
from typing import Annotated
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_pipeline.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/cli/main.py tests/test_cli_pipeline.py
git commit -m "feat(cli): add containerize-v2 command"
```

---

### Task 6.3: Add cache invalidation logic

**Files:**
- Create: `src/wunderunner/pipeline/cache.py`
- Test: `tests/test_pipeline_cache.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_cache.py
"""Tests for cache invalidation."""

import pytest
from pathlib import Path
import time

from wunderunner.pipeline.cache import should_rebuild_research, should_replan


def test_should_rebuild_when_no_research(tmp_path: Path):
    """Should rebuild if research.md doesn't exist."""
    assert should_rebuild_research(tmp_path) is True


def test_should_not_rebuild_when_fresh(tmp_path: Path):
    """Should not rebuild if research.md is newer than manifest."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Research")

    # Create older manifest
    (tmp_path / "pyproject.toml").write_text("[project]")
    time.sleep(0.01)  # Ensure mtime difference
    (wunderunner_dir / "research.md").write_text("# Updated Research")

    assert should_rebuild_research(tmp_path) is False


def test_should_rebuild_when_manifest_changed(tmp_path: Path):
    """Should rebuild if manifest is newer than research.md."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Research")

    time.sleep(0.01)  # Ensure mtime difference
    (tmp_path / "pyproject.toml").write_text("[project]\n# changed")

    assert should_rebuild_research(tmp_path) is True


def test_should_replan_when_no_plan(tmp_path: Path):
    """Should replan if plan.md doesn't exist."""
    assert should_replan(tmp_path) is True


def test_should_replan_when_research_changed(tmp_path: Path):
    """Should replan if research.md is newer than plan.md."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "plan.md").write_text("# Plan")

    time.sleep(0.01)
    (wunderunner_dir / "research.md").write_text("# Updated Research")

    assert should_replan(tmp_path) is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_cache.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write cache module**

```python
# src/wunderunner/pipeline/cache.py
"""Cache invalidation logic for pipeline artifacts."""

from pathlib import Path

from wunderunner.pipeline.artifacts import get_artifact_path

# Files that trigger research invalidation
MANIFEST_FILES = [
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "requirements.txt",
]


def should_rebuild_research(project_dir: Path) -> bool:
    """Check if RESEARCH phase should re-run.

    Returns True if:
    - research.md doesn't exist
    - Any manifest file is newer than research.md

    Args:
        project_dir: Project root directory.

    Returns:
        True if research should be re-run.
    """
    research_path = get_artifact_path(project_dir, "research.md")

    if not research_path.exists():
        return True

    research_mtime = research_path.stat().st_mtime

    for manifest in MANIFEST_FILES:
        manifest_path = project_dir / manifest
        if manifest_path.exists():
            if manifest_path.stat().st_mtime > research_mtime:
                return True

    return False


def should_replan(project_dir: Path) -> bool:
    """Check if PLAN phase should re-run.

    Returns True if:
    - plan.md doesn't exist
    - research.md is newer than plan.md
    - fixes.json is newer than plan.md (constraints changed)

    Args:
        project_dir: Project root directory.

    Returns:
        True if plan should be re-generated.
    """
    plan_path = get_artifact_path(project_dir, "plan.md")

    if not plan_path.exists():
        return True

    plan_mtime = plan_path.stat().st_mtime

    # Check if research changed
    research_path = get_artifact_path(project_dir, "research.md")
    if research_path.exists() and research_path.stat().st_mtime > plan_mtime:
        return True

    # Check if constraints changed
    fixes_path = get_artifact_path(project_dir, "fixes.json")
    if fixes_path.exists() and fixes_path.stat().st_mtime > plan_mtime:
        return True

    return False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_cache.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/cache.py tests/test_pipeline_cache.py
git commit -m "feat(pipeline): add cache invalidation logic"
```

---

### Task 6.4: Integrate cache into runner

**Files:**
- Modify: `src/wunderunner/pipeline/runner.py`
- Modify: `tests/test_pipeline_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_runner.py (append)


@pytest.mark.asyncio
async def test_run_pipeline_uses_cache(tmp_path: Path, mock_plan):
    """run_pipeline skips research if cache valid."""
    # Create cached research
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Cached Research\n## Runtime\n- python")
    (wunderunner_dir / "plan.md").write_text("# Plan\n## Files\n### Dockerfile\n```dockerfile\nFROM x\n```")

    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock) as mock_r:
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock) as mock_p:
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=True, files_written=["Dockerfile"])

                result = await run_pipeline(tmp_path)

    # Research and plan should NOT be called (cache hit)
    mock_r.assert_not_called()
    mock_p.assert_not_called()
    assert result.status == PipelineStatus.SUCCESS
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_runner.py::test_run_pipeline_uses_cache -v`
Expected: FAIL (runner doesn't check cache yet)

**Step 3: Update runner to use cache**

```python
# src/wunderunner/pipeline/runner.py

# Add import at top
from wunderunner.pipeline.cache import should_rebuild_research, should_replan

# Replace the RESEARCH and PLAN sections in run_pipeline with:

        # RESEARCH phase (with cache)
        research_path = get_artifact_path(project_dir, "research.md")
        need_research = rebuild or should_rebuild_research(project_dir)

        if need_research:
            progress("RESEARCH", "Running project analysis...")
            research_result = await run_research(project_dir)
            await write_research(project_dir, research_result)
            progress("RESEARCH", "Complete")

        # PLAN phase (with cache)
        plan_path = get_artifact_path(project_dir, "plan.md")
        need_plan = rebuild or replan or should_replan(project_dir)

        if need_plan:
            progress("PLAN", "Generating containerization plan...")
            await run_plan(project_dir)
            progress("PLAN", "Complete")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/runner.py tests/test_pipeline_runner.py
git commit -m "feat(pipeline): add cache integration to runner"
```

---

### Task 6.5: Add integration test

**Files:**
- Create: `tests/test_pipeline_integration.py`

**Step 1: Write integration test**

```python
# tests/test_pipeline_integration.py
"""Integration tests for complete pipeline."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline import run_pipeline, PipelineStatus
from wunderunner.pipeline.models import (
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
    ContainerizationPlan,
    VerificationStep,
)


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "testapp"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn"]
""")
    (tmp_path / "app.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""")
    (tmp_path / "uv.lock").write_text("# lock")
    return tmp_path


@pytest.mark.asyncio
async def test_full_pipeline_success(python_project: Path):
    """Test complete pipeline from research to success."""
    # Mock specialist agents to return expected data
    runtime = RuntimeFindings(language="python", version="3.11", framework="fastapi")
    deps = DependencyFindings(package_manager="uv", start_command="uvicorn app:app")
    config = ConfigFindings()
    services = ServiceFindings()

    plan = ContainerizationPlan(
        summary="Python FastAPI app",
        dockerfile="""FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0"]
""",
        verification=[
            VerificationStep(command="docker build -t app .", expected="exit 0"),
        ],
        reasoning="Standard FastAPI setup",
        constraints_honored=[],
    )

    # Mock all the agent runs
    with patch("wunderunner.pipeline.research.specialists.runtime.agent.run", new_callable=AsyncMock) as mock_rt:
        with patch("wunderunner.pipeline.research.specialists.dependencies.agent.run", new_callable=AsyncMock) as mock_dp:
            with patch("wunderunner.pipeline.research.specialists.config.agent.run", new_callable=AsyncMock) as mock_cf:
                with patch("wunderunner.pipeline.research.specialists.services.agent.run", new_callable=AsyncMock) as mock_sv:
                    with patch("wunderunner.pipeline.plan.agent.agent.run", new_callable=AsyncMock) as mock_pl:
                        with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
                            # Set up mocks
                            mock_rt.return_value = AsyncMock(output=runtime)
                            mock_dp.return_value = AsyncMock(output=deps)
                            mock_cf.return_value = AsyncMock(output=config)
                            mock_sv.return_value = AsyncMock(output=services)
                            mock_pl.return_value = AsyncMock(output=plan)

                            # Mock docker build success
                            proc = MagicMock()
                            proc.returncode = 0
                            proc.communicate = AsyncMock(return_value=(b"Built!", b""))
                            mock_proc.return_value = proc

                            # Run pipeline
                            result = await run_pipeline(python_project)

    # Verify result
    assert result.status == PipelineStatus.SUCCESS
    assert result.attempts == 1
    assert "Dockerfile" in result.files_written

    # Verify files were created
    assert (python_project / "Dockerfile").exists()
    assert (python_project / ".wunderunner" / "research.md").exists()
    assert (python_project / ".wunderunner" / "plan.md").exists()

    # Verify Dockerfile content
    dockerfile_content = (python_project / "Dockerfile").read_text()
    assert "FROM python:3.11-slim" in dockerfile_content
    assert "uvicorn" in dockerfile_content
```

**Step 2: Run test**

Run: `uv run pytest tests/test_pipeline_integration.py -v`
Expected: PASS (once all previous tasks complete)

**Step 3: Commit**

```bash
git add tests/test_pipeline_integration.py
git commit -m "test(pipeline): add integration test"
```

---

**Part 6 Complete.** CLI integration with cache and full pipeline runner.

---

## Final Steps

### Commit all changes

```bash
git add -A
git commit -m "feat(pipeline): complete RESEARCH → PLAN → IMPLEMENT pipeline"
```

### Run full test suite

```bash
uv run pytest tests/test_pipeline*.py -v
```

### Update CLAUDE.md with new command

Add to project CLAUDE.md:

```markdown
## Pipeline v2

New containerization pipeline with RESEARCH → PLAN → IMPLEMENT phases:

```bash
wxr containerize-v2 ./path/to/project
wxr containerize-v2 ./project --rebuild    # Force re-analyze
wxr containerize-v2 ./project --replan     # Force re-plan
wxr containerize-v2 ./project --max-attempts 10
```

Artifacts stored in `.wunderunner/`:
- `research.md` - Project analysis
- `plan.md` - Containerization plan with exact file contents
- `fixes.json` - Fix history and constraints
- `error-analysis.md` - Error diagnosis (when errors occur)
- `fix-plan.md` - Fix plan (when errors occur)
- `logs/` - Build/verification logs
```

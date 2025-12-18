"""Tests for PLAN phase runner."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.pipeline.plan.runner import run_plan


@pytest.fixture
def project_with_research(tmp_path: Path) -> Path:
    """Create project with research.md artifact."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("""# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11

## Dependencies
- **Package Manager:** uv

## Configuration
No environment variables detected.

## Backing Services
No backing services detected.
""")
    return tmp_path


@pytest.mark.asyncio
async def test_run_plan_reads_research_and_generates(project_with_research: Path):
    """run_plan reads research.md and generates plan."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Simple Python app",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        result = await run_plan(project_with_research)

    assert isinstance(result, ContainerizationPlan)


@pytest.mark.asyncio
async def test_run_plan_writes_artifact(project_with_research: Path):
    """run_plan writes plan.md artifact."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        verification=[],
        reasoning="Simple",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        await run_plan(project_with_research)

    plan_path = project_with_research / ".wunderunner" / "plan.md"
    assert plan_path.exists()
    content = plan_path.read_text()
    assert "FROM python:3.11-slim" in content


@pytest.mark.asyncio
async def test_run_plan_raises_if_no_research(tmp_path: Path):
    """run_plan raises if research.md missing."""
    with pytest.raises(FileNotFoundError):
        await run_plan(tmp_path)

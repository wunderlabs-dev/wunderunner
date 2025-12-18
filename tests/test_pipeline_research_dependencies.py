"""Tests for dependency-analyzer specialist."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import DependencyFindings, NativeDependency
from wunderunner.pipeline.research.specialists.dependencies import analyze_dependencies


@pytest.fixture
def python_project_with_native(tmp_path: Path) -> Path:
    """Create a Python project with native dependencies."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
dependencies = ["psycopg2-binary", "pillow"]
""")
    (tmp_path / "uv.lock").write_text("# lock")
    return tmp_path


@pytest.mark.asyncio
async def test_analyze_dependencies_returns_findings(python_project_with_native: Path):
    """analyze_dependencies returns DependencyFindings."""
    mock_result = DependencyFindings(
        package_manager="uv",
        native_deps=[
            NativeDependency(
                name="libpq-dev", reason="psycopg2 requires PostgreSQL client"
            )
        ],
        start_command="uvicorn app:app --host 0.0.0.0",
    )

    with patch(
        "wunderunner.pipeline.research.specialists.dependencies.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await analyze_dependencies(python_project_with_native)

    assert isinstance(result, DependencyFindings)
    assert result.package_manager == "uv"
    assert len(result.native_deps) == 1

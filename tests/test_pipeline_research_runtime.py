"""Tests for runtime-detector specialist."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import RuntimeFindings
from wunderunner.pipeline.research.specialists.runtime import detect_runtime


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "myapp"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn"]
""")
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    (tmp_path / "uv.lock").write_text("# lock file")
    return tmp_path


@pytest.mark.asyncio
async def test_detect_runtime_returns_findings(python_project: Path):
    """detect_runtime returns RuntimeFindings model."""
    # Mock the agent run to return expected findings
    mock_result = RuntimeFindings(
        language="python",
        version="3.11",
        framework="fastapi",
        entrypoint="src/main.py",
    )

    with patch(
        "wunderunner.pipeline.research.specialists.runtime.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await detect_runtime(python_project)

    assert isinstance(result, RuntimeFindings)
    assert result.language == "python"

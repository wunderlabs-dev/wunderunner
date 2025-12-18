"""Tests for artifact file I/O."""

from pathlib import Path

import pytest

from wunderunner.pipeline.artifacts import (
    get_artifact_path,
    write_research,
)
from wunderunner.pipeline.models import (
    ConfigFindings,
    DependencyFindings,
    ResearchResult,
    RuntimeFindings,
    ServiceFindings,
)


@pytest.mark.asyncio
async def test_write_and_read_research(tmp_path: Path):
    """Can write research.md and read it back."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="python"),
        dependencies=DependencyFindings(package_manager="pip"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )

    await write_research(tmp_path, result)

    research_path = get_artifact_path(tmp_path, "research.md")
    assert research_path.exists()

    content = research_path.read_text()
    assert "python" in content


def test_get_artifact_path(tmp_path: Path):
    """get_artifact_path returns correct path in .wunderunner."""
    path = get_artifact_path(tmp_path, "research.md")
    assert path == tmp_path / ".wunderunner" / "research.md"

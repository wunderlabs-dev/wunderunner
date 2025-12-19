"""Tests for log capture."""

from pathlib import Path

import pytest

from wunderunner.pipeline.implement.logs import get_log_path, save_logs


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

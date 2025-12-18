"""Tests for config-finder specialist."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import ConfigFindings, EnvVarFinding
from wunderunner.pipeline.research.specialists.config import find_config


@pytest.fixture
def project_with_env(tmp_path: Path) -> Path:
    """Create a project with env configuration."""
    (tmp_path / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\nPORT=3000\n")
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "config.py").write_text("""
import os
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.getenv("API_KEY")
PORT = os.getenv("PORT", "3000")
""")
    return tmp_path


@pytest.mark.asyncio
async def test_find_config_returns_findings(project_with_env: Path):
    """find_config returns ConfigFindings."""
    mock_result = ConfigFindings(
        env_vars=[
            EnvVarFinding(
                name="DATABASE_URL", required=True, secret=True, service="postgres"
            ),
            EnvVarFinding(name="API_KEY", required=False, secret=True),
            EnvVarFinding(name="PORT", required=False, default="3000"),
        ],
        config_files=[".env.example"],
    )

    with patch(
        "wunderunner.pipeline.research.specialists.config.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await find_config(project_with_env)

    assert isinstance(result, ConfigFindings)
    assert len(result.env_vars) == 3
    assert result.env_vars[0].secret is True

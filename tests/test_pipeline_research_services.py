"""Tests for service-detector specialist."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import ServiceFinding, ServiceFindings
from wunderunner.pipeline.research.specialists.services import detect_services


@pytest.fixture
def project_with_db(tmp_path: Path) -> Path:
    """Create a project with database usage."""
    (tmp_path / "docker-compose.yaml").write_text("""
services:
  db:
    image: postgres:15
  redis:
    image: redis:7
""")
    return tmp_path


@pytest.mark.asyncio
async def test_detect_services_returns_findings(project_with_db: Path):
    """detect_services returns ServiceFindings."""
    mock_result = ServiceFindings(
        services=[
            ServiceFinding(type="postgres", version="15", env_var="DATABASE_URL"),
            ServiceFinding(type="redis", version="7", env_var="REDIS_URL"),
        ]
    )

    with patch(
        "wunderunner.pipeline.research.specialists.services.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await detect_services(project_with_db)

    assert isinstance(result, ServiceFindings)
    assert len(result.services) == 2
    assert result.services[0].type == "postgres"

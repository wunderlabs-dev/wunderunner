"""Tests for PLAN phase agent."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep
from wunderunner.pipeline.plan.agent import generate_plan


@pytest.fixture
def research_content() -> str:
    """Sample research.md content."""
    return """# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11
- **Framework:** fastapi
- **Entrypoint:** src/main.py

## Dependencies
- **Package Manager:** uv
- **Start Command:** `uvicorn src.main:app --host 0.0.0.0`

## Configuration

### Environment Variables
| Name | Required | Secret | Service | Default |
|------|----------|--------|---------|---------|
| DATABASE_URL | Yes | Yes | postgres | - |

## Backing Services
- **postgres** (v15) → `DATABASE_URL`
"""


@pytest.mark.asyncio
async def test_generate_plan_returns_containerization_plan(tmp_path: Path, research_content: str):
    """generate_plan returns ContainerizationPlan with exact content."""
    mock_plan = ContainerizationPlan(
        summary="Python 3.11 FastAPI app with PostgreSQL",
        dockerfile="""FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY src/ ./src/
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0"]
""",
        compose="""services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      - DATABASE_URL
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
""",
        verification=[
            VerificationStep(
                command="docker compose build", expected="exit 0", phase="BUILD"
            ),
            VerificationStep(
                command="docker compose up -d", expected="containers start", phase="START"
            ),
        ],
        reasoning="Using uv for fast dependency resolution, slim image for size",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=[])

    assert isinstance(result, ContainerizationPlan)
    assert "FROM python:3.11" in result.dockerfile
    assert "postgres:15" in result.compose
    assert len(result.verification) == 2


@pytest.mark.asyncio
async def test_generate_plan_honors_constraints(tmp_path: Path, research_content: str):
    """generate_plan includes constraints in output."""
    constraints = ["MUST use python:3.11-slim base image", "MUST include pandas"]

    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Honoring constraints",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=constraints)

    assert result.constraints_honored == constraints

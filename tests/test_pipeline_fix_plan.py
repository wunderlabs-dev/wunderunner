"""Tests for FIX-PLAN agent."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.errors.fix_plan import run_fix_plan
from wunderunner.pipeline.models import ErrorAnalysis, FixPlan


@pytest.fixture
def error_analysis() -> ErrorAnalysis:
    """Sample error analysis."""
    return ErrorAnalysis(
        error_summary="Missing build script",
        root_cause="package.json has no build script",
        fix_history_review="No previous attempts",
        exhaustion_status=[],
        recommendation="continue",
        suggested_approach="Change CMD to use npm run dev",
    )


@pytest.fixture
def current_plan() -> str:
    """Current plan.md content."""
    return """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "build"]
```
"""


@pytest.mark.asyncio
async def test_run_fix_plan_returns_plan(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan returns FixPlan with updated Dockerfile."""
    mock_plan = FixPlan(
        summary="Change build command to dev",
        dockerfile="""FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]
""",
        changes_description="Changed CMD from 'npm run build' to 'npm run dev'",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=["MUST use node:20-slim"],
        )

    assert isinstance(result, FixPlan)
    assert '"dev"' in result.dockerfile
    assert result.changes_description != ""


@pytest.mark.asyncio
async def test_run_fix_plan_honors_constraints(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan includes honored constraints."""
    constraints = ["MUST use node:20-slim", "MUST NOT use multi-stage"]

    mock_plan = FixPlan(
        summary="Fix",
        dockerfile="FROM node:20-slim\n",
        changes_description="Fixed",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=constraints,
        )

    assert result.constraints_honored == constraints

"""Tests for RESEARCH phase orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.pipeline.models import (
    ConfigFindings,
    DependencyFindings,
    ResearchResult,
    RuntimeFindings,
    ServiceFindings,
)
from wunderunner.pipeline.research.orchestrator import run_research


@pytest.fixture
def mock_specialists():
    """Mock all specialist functions."""
    runtime = RuntimeFindings(language="python", version="3.11", framework="fastapi")
    deps = DependencyFindings(package_manager="uv", start_command="uvicorn app:app")
    config = ConfigFindings(env_vars=[], config_files=[])
    services = ServiceFindings(services=[])

    return {
        "detect_runtime": AsyncMock(return_value=runtime),
        "analyze_dependencies": AsyncMock(return_value=deps),
        "find_config": AsyncMock(return_value=config),
        "detect_services": AsyncMock(return_value=services),
    }


@pytest.mark.asyncio
async def test_run_research_calls_all_specialists(tmp_path: Path, mock_specialists):
    """run_research executes all specialists in parallel."""
    with patch.multiple(
        "wunderunner.pipeline.research.orchestrator", **mock_specialists
    ):
        result = await run_research(tmp_path)

    assert isinstance(result, ResearchResult)
    assert result.runtime.language == "python"
    assert result.dependencies.package_manager == "uv"


@pytest.mark.asyncio
async def test_run_research_runs_in_parallel(tmp_path: Path, mock_specialists):
    """run_research uses asyncio.gather for parallel execution."""
    import asyncio

    call_times = []

    async def track_runtime(*args, **kwargs):
        call_times.append(("runtime", asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return mock_specialists["detect_runtime"].return_value

    async def track_deps(*args, **kwargs):
        call_times.append(("deps", asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return mock_specialists["analyze_dependencies"].return_value

    with (
        patch("wunderunner.pipeline.research.orchestrator.detect_runtime", track_runtime),
        patch(
            "wunderunner.pipeline.research.orchestrator.analyze_dependencies", track_deps
        ),
        patch(
            "wunderunner.pipeline.research.orchestrator.find_config",
            mock_specialists["find_config"],
        ),
        patch(
            "wunderunner.pipeline.research.orchestrator.detect_services",
            mock_specialists["detect_services"],
        ),
    ):
        await run_research(tmp_path)

    # Both should start at nearly the same time (parallel)
    assert len(call_times) >= 2
    time_diff = abs(call_times[0][1] - call_times[1][1])
    assert time_diff < 0.005  # Within 5ms = parallel

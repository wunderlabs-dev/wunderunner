"""RESEARCH phase orchestrator.

Spawns specialist agents in parallel, waits for all, combines results.
"""

import asyncio
from pathlib import Path

from wunderunner.pipeline.models import ResearchResult
from wunderunner.pipeline.research.specialists.config import find_config
from wunderunner.pipeline.research.specialists.dependencies import analyze_dependencies
from wunderunner.pipeline.research.specialists.runtime import detect_runtime
from wunderunner.pipeline.research.specialists.services import detect_services


async def run_research(project_dir: Path) -> ResearchResult:
    """Execute RESEARCH phase with parallel specialists.

    Spawns all specialist agents concurrently using asyncio.gather,
    waits for all to complete, then combines their outputs.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ResearchResult combining all specialist findings.
    """
    # Run all specialists in parallel
    runtime, dependencies, config, services = await asyncio.gather(
        detect_runtime(project_dir),
        analyze_dependencies(project_dir),
        find_config(project_dir),
        detect_services(project_dir),
    )

    return ResearchResult(
        runtime=runtime,
        dependencies=dependencies,
        config=config,
        services=services,
    )

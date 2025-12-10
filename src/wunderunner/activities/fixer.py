"""Improvement activity - analyzes failures and fixes both Dockerfile and project files."""

import logging
from pathlib import Path

from pydantic_ai import UsageLimits

from wunderunner.agents.generation import improvement as improvement_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import Analysis
from wunderunner.models.context import ContextEntry, EntryType
from wunderunner.models.generation import ImprovementResult
from wunderunner.settings import Generation, get_fallback_model
from wunderunner.storage.context import add_entry, load_context
from wunderunner.workflows.state import Learning

logger = logging.getLogger(__name__)

# Limit tool calls - agent should read error and fix quickly, not explore endlessly
USAGE_LIMITS = UsageLimits(tool_calls_limit=15)


async def improve_dockerfile(
    learning: Learning,
    analysis: Analysis,
    dockerfile_content: str,
    compose_content: str | None,
    project_path: Path,
    attempt_number: int = 1,
) -> ImprovementResult:
    """Analyze a failure and fix both Dockerfile and project files as needed.

    This is a unified improvement agent that can:
    - Analyze build/runtime errors
    - Fix Dockerfile issues (missing build steps, wrong base image, etc.)
    - Fix project files (config conflicts, missing files, etc.)

    Args:
        learning: The error that occurred.
        analysis: Project analysis with structure, dependencies, etc.
        dockerfile_content: Current Dockerfile content.
        compose_content: Current docker-compose.yaml content (if any).
        project_path: Path to project directory.
        attempt_number: Current attempt number for context.

    Returns:
        ImprovementResult with fixed Dockerfile and list of modified files.
    """
    # Load historical context for anti-regression
    context = await load_context(project_path)
    historical_fixes = context.get_dockerfile_fixes() if context else []

    # Determine exit code from error type
    exit_code = 1
    if "timeout" in learning.error_message.lower():
        exit_code = 124  # Timeout exit code

    prompt = improvement_agent.USER_PROMPT.render(
        attempt_number=attempt_number,
        dockerfile=dockerfile_content,
        phase=learning.phase,
        exit_code=exit_code,
        error_message=learning.error_message,
        historical_fixes=historical_fixes,
    )

    logger.debug("Improvement prompt:\n%s", prompt)

    deps = AgentDeps(project_dir=project_path)

    try:
        result = await improvement_agent.agent.run(
            prompt,
            model=get_fallback_model(Generation.DOCKERFILE),
            deps=deps,
            usage_limits=USAGE_LIMITS,
        )
        improvement = result.output

        logger.info(
            "Improvement (confidence %d/10): %s",
            improvement.confidence,
            improvement.reasoning,
        )
        if improvement.files_modified:
            logger.info("  Files modified: %s", improvement.files_modified)

        # Record improvement to context
        entry = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            error=learning.error_message[:500],  # Truncate long errors
            fix=f"Improved (confidence {improvement.confidence}/10)",
            explanation=improvement.reasoning,
        )
        await add_entry(project_path, entry)

        return improvement
    except Exception as e:
        logger.warning("Improvement agent failed: %s", e)
        # Return unchanged Dockerfile on failure
        return ImprovementResult(
            dockerfile=dockerfile_content,
            confidence=0,
            reasoning=f"Improvement agent error: {e}",
            files_modified=[],
        )

"""Project fixer activity."""

import logging
from pathlib import Path

from wunderunner.agents.generation import fixer as fixer_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.analysis import Analysis
from wunderunner.workflows.state import Learning

logger = logging.getLogger(__name__)


async def fix_project(
    learning: Learning,
    analysis: Analysis,
    dockerfile_content: str,
    compose_content: str | None,
    project_path: Path,
) -> fixer_agent.FixResult:
    """Attempt to fix project files based on error.

    Args:
        learning: The error that occurred.
        analysis: Project analysis with structure, dependencies, etc.
        dockerfile_content: Current Dockerfile content.
        compose_content: Current docker-compose.yaml content (if any).
        project_path: Path to project directory.

    Returns:
        FixResult indicating if fix was made and what changed.
    """
    prompt = fixer_agent.USER_PROMPT.render(
        analysis=analysis.model_dump(),
        phase=learning.phase,
        error_type=learning.error_type,
        error_message=learning.error_message,
        context=learning.context,
        dockerfile=dockerfile_content,
        compose=compose_content,
    )

    deps = AgentDeps(project_dir=project_path)

    try:
        result = await fixer_agent.agent.run(prompt, deps=deps)
        fix_result = result.output

        if fix_result.fixed:
            logger.info("Fixed project: %s", fix_result.explanation)
            for change in fix_result.changes:
                logger.info("  Modified: %s", change)
        else:
            logger.debug("No fix applied: %s", fix_result.explanation)

        return fix_result
    except Exception as e:
        logger.warning("Fixer agent failed: %s", e)
        return fixer_agent.FixResult(
            fixed=False,
            changes=[],
            explanation=f"Fixer agent error: {e}",
        )

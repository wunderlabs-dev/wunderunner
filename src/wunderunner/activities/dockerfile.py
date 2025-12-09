"""Dockerfile generation activity."""

from pathlib import Path

from wunderunner.agents.generation import dockerfile as dockerfile_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import DockerfileError
from wunderunner.models.analysis import Analysis
from wunderunner.workflows.state import Learning


async def generate(
    analysis: Analysis,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
    project_path: Path | None = None,
) -> str:
    """Generate or refine Dockerfile based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this Dockerfile instead of generating fresh.
        project_path: Path to project directory (for tool access).

    Returns:
        Dockerfile content as string.

    Raises:
        DockerfileError: If generation/refinement fails.
    """
    prompt = dockerfile_agent.USER_PROMPT.render(
        analysis=analysis.model_dump(),
        learnings=learnings,
        hints=hints,
        existing_dockerfile=existing,
    )

    # Create deps for tool access (agent can inspect files if needed)
    deps = AgentDeps(project_dir=project_path) if project_path else None

    try:
        result = await dockerfile_agent.agent.run(prompt, deps=deps)
        return result.output
    except Exception as e:
        raise DockerfileError(f"Failed to generate Dockerfile: {e}") from e

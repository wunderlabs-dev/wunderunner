"""Dockerfile generation activity."""

from pathlib import Path

from wunderunner.agents.generation import dockerfile as dockerfile_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import DockerfileError
from wunderunner.models.analysis import Analysis
from wunderunner.workflows.state import Learning


def _format_learnings(learnings: list[Learning]) -> str:
    """Format learnings for the prompt."""
    if not learnings:
        return "None"

    lines = []
    for learning in learnings:
        lines.append(f"- [{learning.phase}] {learning.error_type}: {learning.error_message}")
        if learning.context:
            lines.append(f"  Context: {learning.context}")
    return "\n".join(lines)


def _build_prompt(
    analysis: Analysis,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None,
) -> str:
    """Build the user prompt for the agent."""
    parts = []

    # Project analysis
    parts.append("<project_analysis>")
    parts.append(f"Runtime: {analysis.project_structure.runtime}")
    if analysis.project_structure.runtime_version:
        parts.append(f"Runtime Version: {analysis.project_structure.runtime_version}")
    if analysis.project_structure.framework:
        parts.append(f"Framework: {analysis.project_structure.framework}")
    parts.append(f"Package Manager: {analysis.project_structure.package_manager}")
    if analysis.project_structure.package_manager_version:
        pm_version = analysis.project_structure.package_manager_version
        parts.append(f"Package Manager Version: {pm_version}")
    if analysis.project_structure.entry_point:
        parts.append(f"Entry Point: {analysis.project_structure.entry_point}")
    if analysis.project_structure.dependencies:
        parts.append(f"Key Dependencies: {', '.join(analysis.project_structure.dependencies[:10])}")
    parts.append("</project_analysis>")

    # Build strategy
    parts.append("\n<build_strategy>")
    if analysis.build_strategy.build_command:
        parts.append(f"Build Command: {analysis.build_strategy.build_command}")
    if analysis.build_strategy.start_command:
        parts.append(f"Start Command: {analysis.build_strategy.start_command}")
    if analysis.build_strategy.native_dependencies:
        native_deps = ", ".join(analysis.build_strategy.native_dependencies)
        parts.append(f"Native Dependencies: {native_deps}")
    if analysis.build_strategy.monorepo:
        parts.append(f"Monorepo: Yes (tool: {analysis.build_strategy.monorepo_tool})")
        if analysis.build_strategy.workspaces:
            parts.append(f"Workspaces: {', '.join(analysis.build_strategy.workspaces)}")
    parts.append(f"Multi-stage Recommended: {analysis.build_strategy.multi_stage_recommended}")
    parts.append("</build_strategy>")

    # Environment variables (secrets)
    secrets = [v for v in analysis.env_vars if v.secret]
    if secrets:
        parts.append("\n<secrets>")
        for secret in secrets:
            service_hint = f" (service: {secret.service})" if secret.service else ""
            parts.append(f"- {secret.name}{service_hint}")
        parts.append("</secrets>")

    # Previous learnings
    parts.append("\n<previous_learnings>")
    parts.append(_format_learnings(learnings))
    parts.append("</previous_learnings>")

    # User hints
    if hints:
        parts.append("\n<user_hints>")
        for hint in hints:
            parts.append(f"- {hint}")
        parts.append("</user_hints>")

    # Existing Dockerfile to refine
    if existing:
        parts.append("\n<existing_dockerfile>")
        parts.append(existing)
        parts.append("</existing_dockerfile>")
        parts.append("\nRefine the above Dockerfile to fix the issues in previous_learnings.")
    else:
        parts.append("\nGenerate a new Dockerfile for this project.")

    return "\n".join(parts)


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
    prompt = _build_prompt(analysis, learnings, hints, existing)

    # Create deps for tool access (agent can inspect files if needed)
    deps = AgentDeps(project_dir=project_path) if project_path else None

    try:
        result = await dockerfile_agent.agent.run(prompt, deps=deps)
        return result.output
    except Exception as e:
        raise DockerfileError(f"Failed to generate Dockerfile: {e}") from e

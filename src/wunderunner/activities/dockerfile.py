"""Dockerfile generation activity."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import UsageLimits

from wunderunner.agents.generation import dockerfile as dockerfile_agent
from wunderunner.agents.tools import AgentDeps
from wunderunner.agents.validation import regression as regression_agent
from wunderunner.exceptions import DockerfileError
from wunderunner.models.analysis import Analysis
from wunderunner.models.context import ContextEntry, EntryType
from wunderunner.models.generation import DockerfileResult
from wunderunner.settings import Generation, Validation, get_fallback_model
from wunderunner.storage.context import add_entry, load_context, save_context
from wunderunner.workflows.state import Learning

logger = logging.getLogger(__name__)

# Limit tool calls - the agent has all info it needs from analysis
USAGE_LIMITS = UsageLimits(tool_calls_limit=5)


def _get_default_start_command(runtime: str, framework: str | None) -> str:
    """Get default start command for dev containers.

    Development containers should use dev/watch commands, not production start.
    """
    if runtime == "node":
        # Next.js specifically needs dev mode - npm start requires a build
        if framework and framework.lower() in ("nextjs", "next"):
            return '["npm", "run", "dev"]'
        # Vite, Remix, etc. also prefer dev mode
        if framework and framework.lower() in ("vite", "remix"):
            return '["npm", "run", "dev"]'
        # Default Node.js to dev mode - most projects have a dev script
        return '["npm", "run", "dev"]'

    if runtime == "python":
        if framework and framework.lower() == "fastapi":
            return '["uvicorn", "app:app", "--reload", "--host", "0.0.0.0"]'
        if framework and framework.lower() == "flask":
            return '["flask", "run", "--reload", "--host", "0.0.0.0"]'
        if framework and framework.lower() == "django":
            return '["python", "manage.py", "runserver", "0.0.0.0:8000"]'
        return '["python", "-m", "app"]'

    if runtime == "go":
        return '["go", "run", "."]'

    if runtime == "rust":
        return '["cargo", "run"]'

    # Fallback
    return '["npm", "run", "dev"]'


@dataclass
class GenerateResult:
    """Result of Dockerfile generation including conversation history."""

    result: DockerfileResult
    messages: list[Any]
    """Message history for continuing conversation in next retry."""


async def generate(
    analysis: Analysis,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
    project_path: Path | None = None,
    message_history: list[Any] | None = None,
) -> GenerateResult:
    """Generate or refine Dockerfile based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this Dockerfile instead of generating fresh.
        project_path: Path to project directory (for tool access).
        message_history: Previous conversation messages for stateful generation.

    Returns:
        GenerateResult with dockerfile, confidence, reasoning, and message history.

    Raises:
        DockerfileError: If generation/refinement fails.
    """
    # Load historical context for regression prevention
    context = await load_context(project_path) if project_path else None
    historical_fixes = context.get_dockerfile_fixes() if context else []

    # Extract secrets from analysis
    secrets = [v for v in analysis.env_vars if v.secret]

    # Get runtime-specific template
    analysis_dict = analysis.model_dump()
    project = analysis_dict.get("project_structure", {})
    build = analysis_dict.get("build_strategy", {})
    runtime = project.get("runtime", "node")
    runtime_template = dockerfile_agent.get_runtime_template(runtime, analysis_dict)

    # For dev containers, prefer dev commands over production commands
    framework = project.get("framework")
    default_start = _get_default_start_command(runtime, framework)
    start_command = build.get("start_command") or default_start

    prompt = dockerfile_agent.USER_PROMPT.render(
        runtime=runtime,
        framework=framework,
        package_manager=build.get("package_manager", "npm"),
        lockfile=build.get("lockfile"),
        start_command=start_command,
        port=project.get("port", 3000),
        runtime_template=runtime_template,
        secrets=secrets,
        learnings=learnings,
        hints=hints,
        existing_dockerfile=existing,
    )

    deps = AgentDeps(project_dir=project_path) if project_path else None

    try:
        result = await dockerfile_agent.agent.run(
            prompt,
            model=get_fallback_model(Generation.DOCKERFILE),
            deps=deps,
            message_history=message_history,
            usage_limits=USAGE_LIMITS,
        )
        dockerfile_result = result.output
        new_messages = result.new_messages()

        # Check for regressions if we have historical fixes
        if historical_fixes and project_path:
            dockerfile_result = await _check_regressions(
                dockerfile_result,
                historical_fixes,
                project_path,
            )

        # Record this generation to context
        if project_path:
            entry = ContextEntry(
                entry_type=EntryType.DOCKERFILE,
                fix=f"Generated (confidence {dockerfile_result.confidence}/10)",
                explanation=dockerfile_result.reasoning,
            )
            await add_entry(project_path, entry)

        return GenerateResult(result=dockerfile_result, messages=new_messages)
    except Exception as e:
        raise DockerfileError(f"Failed to generate Dockerfile: {e}") from e


async def _check_regressions(
    result: DockerfileResult,
    historical_fixes: list[ContextEntry],
    project_path: Path,
) -> DockerfileResult:
    """Check for regressions and adjust confidence if needed."""
    prompt = regression_agent.USER_PROMPT.render(
        dockerfile=result.dockerfile,
        historical_fixes=historical_fixes,
        original_confidence=result.confidence,
    )

    try:
        regression_result = await regression_agent.agent.run(
            prompt,
            model=get_fallback_model(Validation.DOCKERFILE),
        )
        check = regression_result.output

        if check.has_regression:
            # Record violation to context
            context = await load_context(project_path)
            context.violation_count += 1
            await save_context(project_path, context)

            # Return adjusted result
            return DockerfileResult(
                dockerfile=result.dockerfile,
                confidence=check.adjusted_confidence,
                reasoning=f"{result.reasoning} [REGRESSION: {', '.join(check.violations)}]",
            )

        return result
    except (RuntimeError, ValueError, OSError) as e:
        logger.warning("Regression check failed, returning original result: %s", e)
        return result

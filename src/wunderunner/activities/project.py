"""Project analysis activity."""

import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError

from wunderunner.agents.analysis import (
    build_strategy,
    code_style,
    env_vars,
    project_structure,
    secrets,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import AnalyzeError
from wunderunner.models.analysis import Analysis, EnvVar
from wunderunner.settings import get_settings

logger = logging.getLogger(__name__)


def _merge_env_vars(env_vars: list[EnvVar], secrets: list[EnvVar]) -> list[EnvVar]:
    """Merge env vars and secrets, deduplicating by name. Secrets take precedence."""
    by_name: dict[str, EnvVar] = {}
    for var in env_vars:
        by_name[var.name] = var
    for secret in secrets:
        by_name[secret.name] = secret
    return list(by_name.values())


async def analyze(path: Path, rebuild: bool = False) -> Analysis:
    """Analyze project structure and dependencies.

    Runs 5 specialized agents to comprehensively analyze the project:
    1. Project structure (framework, runtime, dependencies)
    2. Build strategy (monorepo, build commands)
    3. Environment variables
    4. Secrets and API keys
    5. Code style and tooling

    Args:
        path: Path to the project directory.
        rebuild: If True, skip cache and re-analyze.

    Returns:
        Combined Analysis result.

    Raises:
        AnalyzeError: If analysis fails.
    """
    settings = get_settings()
    cache_path = path / settings.cache_dir / settings.analysis_cache_file

    if not rebuild and cache_path.exists():
        try:
            return Analysis.model_validate_json(cache_path.read_text())
        except (ValidationError, OSError, ValueError) as e:
            logger.warning("Failed to load analysis cache from %s: %s", cache_path, e)

    deps = AgentDeps(project_dir=path)

    try:
        structure, build, env, secret, style = await asyncio.gather(
            project_structure.agent.run(project_structure.USER_PROMPT, deps=deps),
            build_strategy.agent.run(build_strategy.USER_PROMPT, deps=deps),
            env_vars.agent.run(env_vars.USER_PROMPT, deps=deps),
            secrets.agent.run(secrets.USER_PROMPT, deps=deps),
            code_style.agent.run(code_style.USER_PROMPT, deps=deps),
        )
    except Exception as e:
        raise AnalyzeError(f"Analysis failed: {e}") from e

    all_env = _merge_env_vars(env.output, secret.output)

    analysis = Analysis(
        project_structure=structure.output,
        build_strategy=build.output,
        env_vars=all_env,
        code_style=style.output,
    )

    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(analysis.model_dump_json(indent=2))

    return analysis

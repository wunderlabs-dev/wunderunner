"""Project analysis activity."""

from pathlib import Path

from wunderunner.agents.analysis import (
    build_strategy_agent,
    code_style_agent,
    env_vars_agent,
    project_structure_agent,
    secrets_agent,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.exceptions import AnalyzeError
from wunderunner.models.analysis import Analysis, EnvVar

CACHE_DIR = ".wunderunner"
CACHE_FILE = "analysis.json"


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
    cache_path = path / CACHE_DIR / CACHE_FILE

    if not rebuild and cache_path.exists():
        try:
            return Analysis.model_validate_json(cache_path.read_text())
        except Exception:
            pass  # Cache invalid, re-analyze

    deps = AgentDeps(project_dir=path)

    try:
        structure_result = await project_structure_agent.run(deps=deps)
        build_result = await build_strategy_agent.run(deps=deps)
        env_result = await env_vars_agent.run(deps=deps)
        secrets_result = await secrets_agent.run(deps=deps)
        style_result = await code_style_agent.run(deps=deps)
    except Exception as e:
        raise AnalyzeError(f"Analysis failed: {e}") from e

    all_env_vars = _merge_env_vars(env_result.output, secrets_result.output)

    analysis = Analysis(
        project_structure=structure_result.output,
        build_strategy=build_result.output,
        env_vars=all_env_vars,
        code_style=style_result.output,
    )

    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(analysis.model_dump_json(indent=2))

    return analysis

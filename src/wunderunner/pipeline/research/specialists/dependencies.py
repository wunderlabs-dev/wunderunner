"""Dependency-analyzer specialist agent.

Identifies: package manager, native deps, build/start commands.
Documentarian framing: reports what exists, does NOT suggest alternatives.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import DependencyFindings
from wunderunner.settings import Analysis, get_model

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its dependency configuration.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest switching package managers
- Recommend removing dependencies
- Critique dependency choices
- Add editorial commentary

Focus on facts only.

<package_manager_detection>
CRITICAL: The lockfile determines the package manager, NOT manifest declarations.

Python (check_files_exist FIRST):
- uv.lock exists → "uv"
- poetry.lock exists → "poetry"
- Pipfile.lock exists → "pipenv"
- requirements.txt only → "pip"

Node.js (check_files_exist FIRST):
- package-lock.json exists → "npm"
- yarn.lock exists → "yarn"
- pnpm-lock.yaml exists → "pnpm"
- bun.lock exists → "bun"
IGNORE packageManager field in package.json if lockfile doesn't match.

Go: always "go mod"
Rust: always "cargo"
</package_manager_detection>

<native_dependency_detection>
These packages require native/system libraries:

Python:
- psycopg2, psycopg2-binary → libpq-dev
- pillow → libjpeg-dev, zlib1g-dev
- lxml → libxml2-dev, libxslt1-dev
- cryptography → libffi-dev, libssl-dev
- numpy, scipy → libblas-dev, liblapack-dev (for building from source)

Node.js:
- sharp → vips
- canvas → cairo, pango, libjpeg
- bcrypt → python, make, g++
- node-gyp dependencies → python, make, g++
</native_dependency_detection>

<command_detection>
Build commands - look in:
- package.json scripts.build
- pyproject.toml [tool.hatch.build] or presence of build backend
- Makefile targets

Start commands - look in:
- package.json scripts.start
- pyproject.toml [project.scripts]
- Procfile
- Dockerfile CMD (if exists)
</command_detection>

<workflow>
TURN 1 - Check lockfiles and manifests (batch these):
- check_files_exist(["uv.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"])
- read_file("pyproject.toml")
- read_file("package.json")
- read_file("Makefile")

TURN 2 - Check for native deps (batch these):
- read_file("requirements.txt") if Python
- grep("psycopg|pillow|lxml|cryptography", "pyproject.toml") if Python
- grep("sharp|canvas|bcrypt", "package.json") if Node

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = (
    "Analyze this project's dependencies, package manager, "
    "native requirements, and build/start commands."
)

agent = Agent(
    model=get_model(Analysis.BUILD_STRATEGY),  # Reuse existing model tier
    output_type=DependencyFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def analyze_dependencies(project_dir: Path) -> DependencyFindings:
    """Run the dependency-analyzer specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        DependencyFindings with package manager, native deps, commands.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.BUILD_STRATEGY),
    )
    return result.output

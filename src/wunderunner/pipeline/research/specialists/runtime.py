"""Runtime-detector specialist agent.

Identifies: language, version, framework, entrypoint.
Documentarian framing: reports what exists, does NOT suggest improvements.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import RuntimeFindings
from wunderunner.settings import get_model, Analysis

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its runtime configuration.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest improvements or upgrades
- Critique version choices
- Recommend different frameworks
- Add editorial commentary

Focus on facts only.

<detection_rules>
Check for these files to identify runtime:

Python:
- pyproject.toml, setup.py, requirements.txt → language: "python"
- Version from: requires-python, .python-version, runtime.txt
- Framework from dependencies: fastapi, django, flask, starlette

Node.js:
- package.json → language: "node"
- Version from: .nvmrc, .node-version, engines.node in package.json
- Framework from dependencies: next, express, fastify, nestjs, remix

Go:
- go.mod → language: "go"
- Version from: go directive in go.mod
- Framework from imports: gin, echo, fiber

Rust:
- Cargo.toml → language: "rust"
- Version from: rust-version in Cargo.toml, rust-toolchain.toml
</detection_rules>

<entrypoint_detection>
Python: Look for [project.scripts], main.py, app.py, src/main.py, src/app.py
Node.js: Look for "main" or "bin" in package.json, index.js, src/index.ts
Go: Look for main.go, cmd/*/main.go
Rust: Look for src/main.rs, src/bin/*.rs
</entrypoint_detection>

<workflow>
TURN 1 - Check manifest files (batch these):
- read_file("pyproject.toml")
- read_file("package.json")
- read_file("go.mod")
- read_file("Cargo.toml")

TURN 2 - Check version files (batch these):
- read_file(".python-version")
- read_file(".nvmrc")
- read_file(".node-version")
- check_files_exist(["uv.lock", "poetry.lock", "package-lock.json", "yarn.lock"])

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = "Detect this project's runtime, version, framework, and entrypoint."

agent = Agent(
    model=get_model(Analysis.PROJECT_STRUCTURE),  # Reuse existing model tier
    output_type=RuntimeFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def detect_runtime(project_dir: Path) -> RuntimeFindings:
    """Run the runtime-detector specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        RuntimeFindings with detected language, version, framework, entrypoint.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.PROJECT_STRUCTURE),
    )
    return result.output

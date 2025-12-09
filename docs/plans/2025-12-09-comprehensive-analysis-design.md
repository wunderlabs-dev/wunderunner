# Comprehensive Analysis Design

## Overview

Implement the `analyze` activity with 5 specialized Pydantic AI agents that explore a project using filesystem tools, producing a comprehensive `Analysis` result for Dockerfile generation.

## Design Decisions

- **General purpose** - Supports any runtime (Node, Python, Go, Rust, etc.)
- **Tool-based exploration** - AI agents use tools to explore iteratively
- **Separate agents per pass** - 5 independent agents, each specialized
- **Full tool set** - read_file, list_dir, glob, grep, file_stats
- **Tool factory** - Sandboxed tools bound to project directory
- **Pydantic models** - Structured output with validation
- **File-based cache** - `.wunderunner/analysis.json`

## Directory Structure

```
src/wunderunner/
├── agents/
│   ├── __init__.py
│   ├── tools.py              # Tool factory (sandboxed to project)
│   ├── project_structure.py  # Framework, runtime, dependencies
│   ├── build_strategy.py     # Monorepo, build commands, native deps
│   ├── env_vars.py           # Environment variable discovery
│   ├── secrets.py            # API keys, passwords (secret=True)
│   └── code_style.py         # Tooling, existing Docker files
├── models/
│   ├── __init__.py
│   └── analysis.py           # Pydantic models for analysis results
├── prompts/
│   └── analysis/
│       ├── project_structure.j2
│       ├── build_strategy.j2
│       ├── env_vars.j2
│       ├── secrets.j2
│       └── code_style.j2
├── activities/
│   └── project.py            # Orchestrates agents, handles caching
```

## Pydantic Models

**File: `src/wunderunner/models/analysis.py`**

```python
from pydantic import BaseModel

class ProjectStructure(BaseModel):
    """Result of project structure analysis."""
    framework: str | None = None
    runtime: str
    runtime_version: str | None = None
    package_manager: str | None = None
    dependencies: list[str] = []
    entry_point: str | None = None

class BuildStrategy(BaseModel):
    """Result of build strategy analysis."""
    monorepo: bool = False
    monorepo_tool: str | None = None
    workspaces: list[str] = []
    native_dependencies: bool = False
    build_command: str | None = None
    start_command: str | None = None
    multi_stage_recommended: bool = False

class EnvVar(BaseModel):
    """A discovered environment variable."""
    name: str
    required: bool = True
    default: str | None = None
    secret: bool = False
    service: str | None = None

class CodeStyle(BaseModel):
    """Result of code style analysis."""
    uses_typescript: bool = False
    uses_eslint: bool = False
    uses_prettier: bool = False
    test_framework: str | None = None
    dockerfile_exists: bool = False
    compose_exists: bool = False

class Analysis(BaseModel):
    """Combined result of all analysis passes."""
    project_structure: ProjectStructure
    build_strategy: BuildStrategy
    env_vars: list[EnvVar] = []
    code_style: CodeStyle
```

## Tool Factory

**File: `src/wunderunner/agents/tools.py`**

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class AgentDeps:
    """Dependencies injected into agent tools."""
    project_dir: Path
    max_file_size: int = 50_000  # 50KB limit per file read
```

**Tools (registered on each agent):**

| Tool | Purpose | Returns |
|------|---------|---------|
| `read_file(path)` | Read file contents | String (truncated to max_file_size) |
| `list_dir(path=".")` | List directory contents | Newline-separated, dirs suffixed with `/` |
| `glob(pattern)` | Find files by pattern | Newline-separated paths (limit 100) |
| `grep(pattern, path=".")` | Search file contents | Matches with file:line:content format |
| `file_stats(path)` | Get file metadata | Size in bytes, modified time |

All paths validated to stay within project directory (sandbox).

## Agent Structure

**5 agents, each in its own file:**

| Agent | Output Type | Purpose |
|-------|-------------|---------|
| `project_structure.py` | `ProjectStructure` | Framework, runtime, dependencies |
| `build_strategy.py` | `BuildStrategy` | Monorepo, build commands, native deps |
| `env_vars.py` | `list[EnvVar]` | Environment variable discovery |
| `secrets.py` | `list[EnvVar]` | API keys, passwords (returns EnvVars with `secret=True`) |
| `code_style.py` | `CodeStyle` | Tooling, existing Docker files |

**Agent pattern:**

```python
from pydantic_ai import Agent
from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.analysis import ProjectStructure
from wunderunner.settings import get_model

agent = Agent(
    model=get_model("analysis"),
    output_type=ProjectStructure,
    deps_type=AgentDeps,
    system_prompt=_load_system_prompt(),
    defer_model_check=True,
)
register_tools(agent)
```

## Orchestration

**File: `src/wunderunner/activities/project.py`**

```python
CACHE_DIR = ".wunderunner"
CACHE_FILE = "analysis.json"

async def analyze(path: Path, rebuild: bool = False) -> Analysis:
    cache_path = path / CACHE_DIR / CACHE_FILE

    # Check cache unless rebuild requested
    if not rebuild and cache_path.exists():
        return Analysis.model_validate_json(cache_path.read_text())

    # Create sandboxed deps
    deps = AgentDeps(project_dir=path)

    # Run agents in sequence
    structure_result = await project_structure_agent.run(deps=deps)
    build_result = await build_strategy_agent.run(deps=deps)
    env_result = await env_vars_agent.run(deps=deps)
    secrets_result = await secrets_agent.run(deps=deps)
    style_result = await code_style_agent.run(deps=deps)

    # Merge env_vars and secrets (dedupe by name)
    all_env_vars = merge_env_vars(env_result.output, secrets_result.output)

    # Combine results
    analysis = Analysis(
        project_structure=structure_result.output,
        build_strategy=build_result.output,
        env_vars=all_env_vars,
        code_style=style_result.output,
    )

    # Save to cache
    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(analysis.model_dump_json(indent=2))

    return analysis
```

## Caching

- **Location:** `.wunderunner/analysis.json` in the project directory
- **Invalidation:** `--rebuild` flag bypasses cache
- **Format:** JSON via Pydantic's `model_dump_json()`

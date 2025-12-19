## Part 2: Research Phase Specialists

The RESEARCH phase runs multiple specialist subagents in parallel, then synthesizes their outputs into `research.md`.

---

### Task 2.1: Create research module structure

**Files:**
- Create: `src/wunderunner/pipeline/research/__init__.py`
- Create: `src/wunderunner/pipeline/research/specialists/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p src/wunderunner/pipeline/research/specialists
```

**Step 2: Create init files**

```python
# src/wunderunner/pipeline/research/__init__.py
"""RESEARCH phase - parallel specialist agents."""

from wunderunner.pipeline.research.orchestrator import run_research

__all__ = ["run_research"]
```

```python
# src/wunderunner/pipeline/research/specialists/__init__.py
"""Specialist agents for RESEARCH phase."""
```

**Step 3: Commit**

```bash
git add src/wunderunner/pipeline/research/
git commit -m "feat(pipeline): add research phase module structure"
```

---

### Task 2.2: Add runtime-detector specialist

**Files:**
- Create: `src/wunderunner/pipeline/research/specialists/runtime.py`
- Test: `tests/test_pipeline_research_runtime.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_runtime.py
"""Tests for runtime-detector specialist."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import RuntimeFindings
from wunderunner.pipeline.research.specialists.runtime import detect_runtime


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "myapp"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn"]
""")
    (tmp_path / "src" / "main.py").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    (tmp_path / "uv.lock").write_text("# lock file")
    return tmp_path


@pytest.mark.asyncio
async def test_detect_runtime_returns_findings(python_project: Path):
    """detect_runtime returns RuntimeFindings model."""
    # Mock the agent run to return expected findings
    mock_result = RuntimeFindings(
        language="python",
        version="3.11",
        framework="fastapi",
        entrypoint="src/main.py",
    )

    with patch(
        "wunderunner.pipeline.research.specialists.runtime.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await detect_runtime(python_project)

    assert isinstance(result, RuntimeFindings)
    assert result.language == "python"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_runtime.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'wunderunner.pipeline.research.specialists.runtime'"

**Step 3: Write runtime-detector specialist**

```python
# src/wunderunner/pipeline/research/specialists/runtime.py
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_runtime.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/specialists/runtime.py tests/test_pipeline_research_runtime.py
git commit -m "feat(pipeline): add runtime-detector specialist"
```

---

### Task 2.3: Add dependency-analyzer specialist

**Files:**
- Create: `src/wunderunner/pipeline/research/specialists/dependencies.py`
- Test: `tests/test_pipeline_research_dependencies.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_dependencies.py
"""Tests for dependency-analyzer specialist."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import DependencyFindings, NativeDependency
from wunderunner.pipeline.research.specialists.dependencies import analyze_dependencies


@pytest.fixture
def python_project_with_native(tmp_path: Path) -> Path:
    """Create a Python project with native dependencies."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
dependencies = ["psycopg2-binary", "pillow"]
""")
    (tmp_path / "uv.lock").write_text("# lock")
    return tmp_path


@pytest.mark.asyncio
async def test_analyze_dependencies_returns_findings(python_project_with_native: Path):
    """analyze_dependencies returns DependencyFindings."""
    mock_result = DependencyFindings(
        package_manager="uv",
        native_deps=[NativeDependency(name="libpq-dev", reason="psycopg2 requires PostgreSQL client")],
        start_command="uvicorn app:app --host 0.0.0.0",
    )

    with patch(
        "wunderunner.pipeline.research.specialists.dependencies.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await analyze_dependencies(python_project_with_native)

    assert isinstance(result, DependencyFindings)
    assert result.package_manager == "uv"
    assert len(result.native_deps) == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_dependencies.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write dependency-analyzer specialist**

```python
# src/wunderunner/pipeline/research/specialists/dependencies.py
"""Dependency-analyzer specialist agent.

Identifies: package manager, native deps, build/start commands.
Documentarian framing: reports what exists, does NOT suggest alternatives.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import DependencyFindings
from wunderunner.settings import get_model, Analysis

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

USER_PROMPT = "Analyze this project's dependencies, package manager, native requirements, and build/start commands."

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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_dependencies.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/specialists/dependencies.py tests/test_pipeline_research_dependencies.py
git commit -m "feat(pipeline): add dependency-analyzer specialist"
```

---

### Task 2.4: Add config-finder specialist

**Files:**
- Create: `src/wunderunner/pipeline/research/specialists/config.py`
- Test: `tests/test_pipeline_research_config.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_config.py
"""Tests for config-finder specialist."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ConfigFindings, EnvVarFinding
from wunderunner.pipeline.research.specialists.config import find_config


@pytest.fixture
def project_with_env(tmp_path: Path) -> Path:
    """Create a project with env configuration."""
    (tmp_path / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\nPORT=3000\n")
    (tmp_path / "src" / "config.py").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "config.py").write_text("""
import os
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.getenv("API_KEY")
PORT = os.getenv("PORT", "3000")
""")
    return tmp_path


@pytest.mark.asyncio
async def test_find_config_returns_findings(project_with_env: Path):
    """find_config returns ConfigFindings."""
    mock_result = ConfigFindings(
        env_vars=[
            EnvVarFinding(name="DATABASE_URL", required=True, secret=True, service="postgres"),
            EnvVarFinding(name="API_KEY", required=False, secret=True),
            EnvVarFinding(name="PORT", required=False, default="3000"),
        ],
        config_files=[".env.example"],
    )

    with patch(
        "wunderunner.pipeline.research.specialists.config.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await find_config(project_with_env)

    assert isinstance(result, ConfigFindings)
    assert len(result.env_vars) == 3
    assert result.env_vars[0].secret is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_config.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write config-finder specialist**

```python
# src/wunderunner/pipeline/research/specialists/config.py
"""Config-finder specialist agent.

Identifies: environment variables, secrets, config files.
Documentarian framing: reports what exists, does NOT suggest improvements.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import ConfigFindings
from wunderunner.settings import get_model, Analysis

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its configuration requirements.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest different configuration approaches
- Recommend secrets management solutions
- Critique env var naming
- Add editorial commentary

Focus on facts only.

<env_var_detection>
Sources to check:
- .env.example, .env.sample, .env.template
- Code patterns: os.environ["VAR"], os.getenv("VAR"), process.env.VAR
- Config files: config.py, settings.py, config.ts, config.js

For each variable, determine:
- name: The variable name
- required: Does the code crash without it? (environ["X"] = required, getenv("X") = optional)
- secret: Does it contain sensitive data? (passwords, API keys, tokens, connection strings)
- default: Is there a default value?
- service: Is it related to a backing service? (DATABASE_URL → postgres, REDIS_URL → redis)
</env_var_detection>

<secret_patterns>
Variables that are ALWAYS secrets:
- *_API_KEY, *_SECRET, *_TOKEN, *_PASSWORD
- DATABASE_URL, REDIS_URL, *_CONNECTION_STRING
- AWS_*, STRIPE_*, GITHUB_TOKEN

Variables that are NOT secrets:
- PORT, HOST, NODE_ENV, DEBUG, LOG_LEVEL
- PUBLIC_*, NEXT_PUBLIC_*
</secret_patterns>

<config_files>
Report these if they exist:
- .env.example, .env.sample
- config.yaml, config.json
- settings.py, config.py
</config_files>

<workflow>
TURN 1 - Check for config files (batch these):
- check_files_exist([".env.example", ".env.sample", ".env.template"])
- list_dir(".")
- read_file(".env.example") if exists

TURN 2 - Search code for env var usage (batch these):
- grep("environ\\[|getenv\\(|process\\.env\\.", ".")
- read_file("src/config.py") or read_file("config.ts") if exists

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = "Find all environment variables, secrets, and configuration files in this project."

agent = Agent(
    model=get_model(Analysis.ENV_VARS),  # Reuse existing model tier
    output_type=ConfigFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def find_config(project_dir: Path) -> ConfigFindings:
    """Run the config-finder specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ConfigFindings with env vars, secrets, config files.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.ENV_VARS),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/specialists/config.py tests/test_pipeline_research_config.py
git commit -m "feat(pipeline): add config-finder specialist"
```

---

### Task 2.5: Add service-detector specialist

**Files:**
- Create: `src/wunderunner/pipeline/research/specialists/services.py`
- Test: `tests/test_pipeline_research_services.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_services.py
"""Tests for service-detector specialist."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ServiceFindings, ServiceFinding
from wunderunner.pipeline.research.specialists.services import detect_services


@pytest.fixture
def project_with_db(tmp_path: Path) -> Path:
    """Create a project with database usage."""
    (tmp_path / "docker-compose.yaml").write_text("""
services:
  db:
    image: postgres:15
  redis:
    image: redis:7
""")
    return tmp_path


@pytest.mark.asyncio
async def test_detect_services_returns_findings(project_with_db: Path):
    """detect_services returns ServiceFindings."""
    mock_result = ServiceFindings(
        services=[
            ServiceFinding(type="postgres", version="15", env_var="DATABASE_URL"),
            ServiceFinding(type="redis", version="7", env_var="REDIS_URL"),
        ]
    )

    with patch(
        "wunderunner.pipeline.research.specialists.services.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_result),
    ):
        result = await detect_services(project_with_db)

    assert isinstance(result, ServiceFindings)
    assert len(result.services) == 2
    assert result.services[0].type == "postgres"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_services.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write service-detector specialist**

```python
# src/wunderunner/pipeline/research/specialists/services.py
"""Service-detector specialist agent.

Identifies: backing services (databases, caches, queues).
Documentarian framing: reports what exists, does NOT suggest alternatives.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import ServiceFindings
from wunderunner.settings import get_model, Analysis

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its backing services.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest different databases
- Recommend managed services
- Critique architecture choices
- Add editorial commentary

Focus on facts only.

<service_detection>
Check these sources:

1. Existing docker-compose.yaml:
   - Look for service images: postgres, mysql, redis, rabbitmq, mongo, etc.
   - Extract version from image tag

2. Dependencies:
   - psycopg2, asyncpg, pg → postgres
   - mysql-connector, pymysql → mysql
   - redis, ioredis → redis
   - pika, aio-pika, amqplib → rabbitmq
   - pymongo, motor → mongodb
   - elasticsearch-py → elasticsearch

3. Environment variables:
   - DATABASE_URL, POSTGRES_* → postgres
   - MYSQL_* → mysql
   - REDIS_URL, REDIS_* → redis
   - RABBITMQ_*, AMQP_URL → rabbitmq
   - MONGO_*, MONGODB_URI → mongodb
</service_detection>

<version_detection>
Extract version from:
- docker-compose image tags: postgres:15 → version "15"
- Package version constraints (less reliable)
- .tool-versions file

If no version specified, leave as null.
</version_detection>

<workflow>
TURN 1 - Check for existing compose and dependencies (batch these):
- read_file("docker-compose.yaml")
- read_file("docker-compose.yml")
- read_file("pyproject.toml")
- read_file("package.json")

TURN 2 - Search for connection code if needed:
- grep("DATABASE_URL|REDIS_URL|MONGO", ".")

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = "Detect all backing services (databases, caches, queues) used by this project."

agent = Agent(
    model=get_model(Analysis.SECRETS),  # Fast model, simple detection
    output_type=ServiceFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def detect_services(project_dir: Path) -> ServiceFindings:
    """Run the service-detector specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ServiceFindings with detected backing services.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.SECRETS),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_services.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/specialists/services.py tests/test_pipeline_research_services.py
git commit -m "feat(pipeline): add service-detector specialist"
```

---

### Task 2.6: Add research orchestrator

**Files:**
- Create: `src/wunderunner/pipeline/research/orchestrator.py`
- Test: `tests/test_pipeline_research_orchestrator.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_orchestrator.py
"""Tests for RESEARCH phase orchestrator."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import (
    ResearchResult,
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
)
from wunderunner.pipeline.research.orchestrator import run_research


@pytest.fixture
def mock_specialists():
    """Mock all specialist functions."""
    runtime = RuntimeFindings(language="python", version="3.11", framework="fastapi")
    deps = DependencyFindings(package_manager="uv", start_command="uvicorn app:app")
    config = ConfigFindings(env_vars=[], config_files=[])
    services = ServiceFindings(services=[])

    return {
        "wunderunner.pipeline.research.orchestrator.detect_runtime": AsyncMock(return_value=runtime),
        "wunderunner.pipeline.research.orchestrator.analyze_dependencies": AsyncMock(return_value=deps),
        "wunderunner.pipeline.research.orchestrator.find_config": AsyncMock(return_value=config),
        "wunderunner.pipeline.research.orchestrator.detect_services": AsyncMock(return_value=services),
    }


@pytest.mark.asyncio
async def test_run_research_calls_all_specialists(tmp_path: Path, mock_specialists):
    """run_research executes all specialists in parallel."""
    with patch.multiple("wunderunner.pipeline.research.orchestrator", **{
        k.split(".")[-1]: v for k, v in mock_specialists.items()
    }):
        result = await run_research(tmp_path)

    assert isinstance(result, ResearchResult)
    assert result.runtime.language == "python"
    assert result.dependencies.package_manager == "uv"


@pytest.mark.asyncio
async def test_run_research_runs_in_parallel(tmp_path: Path, mock_specialists):
    """run_research uses asyncio.gather for parallel execution."""
    import asyncio

    call_times = []

    async def track_runtime(*args, **kwargs):
        call_times.append(("runtime", asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return mock_specialists["wunderunner.pipeline.research.orchestrator.detect_runtime"].return_value

    async def track_deps(*args, **kwargs):
        call_times.append(("deps", asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return mock_specialists["wunderunner.pipeline.research.orchestrator.analyze_dependencies"].return_value

    with patch("wunderunner.pipeline.research.orchestrator.detect_runtime", track_runtime):
        with patch("wunderunner.pipeline.research.orchestrator.analyze_dependencies", track_deps):
            with patch("wunderunner.pipeline.research.orchestrator.find_config",
                       mock_specialists["wunderunner.pipeline.research.orchestrator.find_config"]):
                with patch("wunderunner.pipeline.research.orchestrator.detect_services",
                           mock_specialists["wunderunner.pipeline.research.orchestrator.detect_services"]):
                    await run_research(tmp_path)

    # Both should start at nearly the same time (parallel)
    assert len(call_times) >= 2
    time_diff = abs(call_times[0][1] - call_times[1][1])
    assert time_diff < 0.005  # Within 5ms = parallel
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_orchestrator.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write research orchestrator**

```python
# src/wunderunner/pipeline/research/orchestrator.py
"""RESEARCH phase orchestrator.

Spawns specialist agents in parallel, waits for all, combines results.
"""

import asyncio
from pathlib import Path

from wunderunner.pipeline.models import ResearchResult
from wunderunner.pipeline.research.specialists.runtime import detect_runtime
from wunderunner.pipeline.research.specialists.dependencies import analyze_dependencies
from wunderunner.pipeline.research.specialists.config import find_config
from wunderunner.pipeline.research.specialists.services import detect_services


async def run_research(project_dir: Path) -> ResearchResult:
    """Execute RESEARCH phase with parallel specialists.

    Spawns all specialist agents concurrently using asyncio.gather,
    waits for all to complete, then combines their outputs.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ResearchResult combining all specialist findings.
    """
    # Run all specialists in parallel
    runtime, dependencies, config, services = await asyncio.gather(
        detect_runtime(project_dir),
        analyze_dependencies(project_dir),
        find_config(project_dir),
        detect_services(project_dir),
    )

    return ResearchResult(
        runtime=runtime,
        dependencies=dependencies,
        config=config,
        services=services,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/orchestrator.py tests/test_pipeline_research_orchestrator.py
git commit -m "feat(pipeline): add RESEARCH phase orchestrator"
```

---

### Task 2.7: Add research synthesis to markdown

**Files:**
- Create: `src/wunderunner/pipeline/research/synthesis.py`
- Test: `tests/test_pipeline_research_synthesis.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_research_synthesis.py
"""Tests for research synthesis to markdown."""

import pytest
from wunderunner.pipeline.models import (
    ResearchResult,
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
    EnvVarFinding,
    ServiceFinding,
    NativeDependency,
)
from wunderunner.pipeline.research.synthesis import synthesize_research


def test_synthesize_research_produces_markdown():
    """synthesize_research converts ResearchResult to markdown."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="python", version="3.11", framework="fastapi"),
        dependencies=DependencyFindings(
            package_manager="uv",
            native_deps=[NativeDependency(name="libpq-dev", reason="psycopg2")],
            start_command="uvicorn app:app",
        ),
        config=ConfigFindings(
            env_vars=[EnvVarFinding(name="DATABASE_URL", secret=True, service="postgres")],
            config_files=[".env.example"],
        ),
        services=ServiceFindings(
            services=[ServiceFinding(type="postgres", version="15")],
        ),
    )

    markdown = synthesize_research(result)

    assert "# Project Research" in markdown
    assert "python" in markdown
    assert "3.11" in markdown
    assert "fastapi" in markdown
    assert "uv" in markdown
    assert "libpq-dev" in markdown
    assert "DATABASE_URL" in markdown
    assert "postgres" in markdown


def test_synthesize_research_handles_empty_sections():
    """synthesize_research handles missing optional data."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="node"),
        dependencies=DependencyFindings(package_manager="npm"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )

    markdown = synthesize_research(result)

    assert "# Project Research" in markdown
    assert "node" in markdown
    assert "npm" in markdown
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_research_synthesis.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write synthesis module**

```python
# src/wunderunner/pipeline/research/synthesis.py
"""Synthesize ResearchResult into markdown artifact."""

from wunderunner.pipeline.models import ResearchResult


def synthesize_research(result: ResearchResult) -> str:
    """Convert ResearchResult to markdown document.

    This produces the research.md artifact that becomes input to PLAN phase.

    Args:
        result: Combined findings from all specialists.

    Returns:
        Markdown string for research.md.
    """
    sections = ["# Project Research\n"]

    # Runtime section
    sections.append("## Runtime\n")
    sections.append(f"- **Language:** {result.runtime.language}")
    if result.runtime.version:
        sections.append(f"- **Version:** {result.runtime.version}")
    if result.runtime.framework:
        sections.append(f"- **Framework:** {result.runtime.framework}")
    if result.runtime.entrypoint:
        sections.append(f"- **Entrypoint:** {result.runtime.entrypoint}")
    sections.append("")

    # Dependencies section
    sections.append("## Dependencies\n")
    sections.append(f"- **Package Manager:** {result.dependencies.package_manager}")
    if result.dependencies.package_manager_version:
        sections.append(f"- **Version:** {result.dependencies.package_manager_version}")
    if result.dependencies.build_command:
        sections.append(f"- **Build Command:** `{result.dependencies.build_command}`")
    if result.dependencies.start_command:
        sections.append(f"- **Start Command:** `{result.dependencies.start_command}`")

    if result.dependencies.native_deps:
        sections.append("\n### Native Dependencies\n")
        for dep in result.dependencies.native_deps:
            sections.append(f"- `{dep.name}`: {dep.reason}")
    sections.append("")

    # Configuration section
    sections.append("## Configuration\n")
    if result.config.config_files:
        sections.append("### Config Files\n")
        for f in result.config.config_files:
            sections.append(f"- `{f}`")
        sections.append("")

    if result.config.env_vars:
        sections.append("### Environment Variables\n")
        sections.append("| Name | Required | Secret | Service | Default |")
        sections.append("|------|----------|--------|---------|---------|")
        for var in result.config.env_vars:
            req = "Yes" if var.required else "No"
            sec = "Yes" if var.secret else "No"
            svc = var.service or "-"
            default = f"`{var.default}`" if var.default else "-"
            sections.append(f"| {var.name} | {req} | {sec} | {svc} | {default} |")
    else:
        sections.append("No environment variables detected.\n")
    sections.append("")

    # Services section
    sections.append("## Backing Services\n")
    if result.services.services:
        for svc in result.services.services:
            version = f" (v{svc.version})" if svc.version else ""
            env = f" → `{svc.env_var}`" if svc.env_var else ""
            sections.append(f"- **{svc.type}**{version}{env}")
    else:
        sections.append("No backing services detected.\n")

    return "\n".join(sections)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_research_synthesis.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/research/synthesis.py tests/test_pipeline_research_synthesis.py
git commit -m "feat(pipeline): add research synthesis to markdown"
```

---

### Task 2.8: Add artifacts module for file I/O

**Files:**
- Create: `src/wunderunner/pipeline/artifacts.py`
- Test: `tests/test_pipeline_artifacts.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_artifacts.py
"""Tests for artifact file I/O."""

import pytest
from pathlib import Path

from wunderunner.pipeline.artifacts import (
    write_research,
    read_research,
    write_plan,
    read_plan,
    get_artifact_path,
)
from wunderunner.pipeline.models import (
    ResearchResult,
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
)


@pytest.mark.asyncio
async def test_write_and_read_research(tmp_path: Path):
    """Can write research.md and read it back."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="python"),
        dependencies=DependencyFindings(package_manager="pip"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )

    await write_research(tmp_path, result)

    research_path = get_artifact_path(tmp_path, "research.md")
    assert research_path.exists()

    content = research_path.read_text()
    assert "python" in content


def test_get_artifact_path(tmp_path: Path):
    """get_artifact_path returns correct path in .wunderunner."""
    path = get_artifact_path(tmp_path, "research.md")
    assert path == tmp_path / ".wunderunner" / "research.md"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_artifacts.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write artifacts module**

```python
# src/wunderunner/pipeline/artifacts.py
"""Read/write artifact files to .wunderunner directory."""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.models import ResearchResult, ContainerizationPlan, FixHistory
from wunderunner.pipeline.research.synthesis import synthesize_research
from wunderunner.settings import get_settings


def get_artifact_path(project_dir: Path, filename: str) -> Path:
    """Get path to an artifact file in .wunderunner directory.

    Args:
        project_dir: Project root directory.
        filename: Artifact filename (research.md, plan.md, etc.)

    Returns:
        Full path to artifact file.
    """
    settings = get_settings()
    return project_dir / settings.cache_dir / filename


async def write_research(project_dir: Path, result: ResearchResult) -> Path:
    """Write research.md artifact.

    Args:
        project_dir: Project root directory.
        result: ResearchResult from RESEARCH phase.

    Returns:
        Path to written file.
    """
    content = synthesize_research(result)
    path = get_artifact_path(project_dir, "research.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


async def read_research(project_dir: Path) -> str:
    """Read research.md artifact content.

    Args:
        project_dir: Project root directory.

    Returns:
        Markdown content of research.md.

    Raises:
        FileNotFoundError: If research.md doesn't exist.
    """
    path = get_artifact_path(project_dir, "research.md")
    async with aiofiles.open(path) as f:
        return await f.read()


async def write_plan(project_dir: Path, plan: ContainerizationPlan) -> Path:
    """Write plan.md artifact.

    Args:
        project_dir: Project root directory.
        plan: ContainerizationPlan from PLAN phase.

    Returns:
        Path to written file.
    """
    content = _format_plan(plan)
    path = get_artifact_path(project_dir, "plan.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_plan(plan: ContainerizationPlan) -> str:
    """Format ContainerizationPlan as markdown."""
    sections = ["# Containerization Plan\n"]

    sections.append(f"## Summary\n{plan.summary}\n")

    if plan.constraints_honored:
        sections.append("## Constraints Honored\n")
        for c in plan.constraints_honored:
            sections.append(f"- [x] {c}")
        sections.append("")

    sections.append("## Files\n")
    sections.append("### Dockerfile\n```dockerfile")
    sections.append(plan.dockerfile)
    sections.append("```\n")

    if plan.compose:
        sections.append("### docker-compose.yaml\n```yaml")
        sections.append(plan.compose)
        sections.append("```\n")

    if plan.verification:
        sections.append("## Verification\n")
        for i, step in enumerate(plan.verification, 1):
            sections.append(f"{i}. `{step.command}` → {step.expected}")
        sections.append("")

    sections.append(f"## Reasoning\n{plan.reasoning}\n")

    return "\n".join(sections)


async def read_plan(project_dir: Path) -> str:
    """Read plan.md artifact content.

    Args:
        project_dir: Project root directory.

    Returns:
        Markdown content of plan.md.

    Raises:
        FileNotFoundError: If plan.md doesn't exist.
    """
    path = get_artifact_path(project_dir, "plan.md")
    async with aiofiles.open(path) as f:
        return await f.read()


async def write_fix_history(project_dir: Path, history: FixHistory) -> Path:
    """Write fixes.json artifact.

    Args:
        project_dir: Project root directory.
        history: FixHistory with attempts and constraints.

    Returns:
        Path to written file.
    """
    path = get_artifact_path(project_dir, "fixes.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(history.model_dump_json(indent=2))

    return path


async def read_fix_history(project_dir: Path) -> FixHistory | None:
    """Read fixes.json artifact.

    Args:
        project_dir: Project root directory.

    Returns:
        FixHistory if file exists, None otherwise.
    """
    path = get_artifact_path(project_dir, "fixes.json")
    if not path.exists():
        return None

    async with aiofiles.open(path) as f:
        content = await f.read()

    return FixHistory.model_validate_json(content)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_artifacts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/artifacts.py tests/test_pipeline_artifacts.py
git commit -m "feat(pipeline): add artifacts module for file I/O"
```

---

**Part 2 Complete.** RESEARCH phase with all specialists, orchestrator, synthesis, and artifact I/O. Next: Part 3 (Plan Phase).

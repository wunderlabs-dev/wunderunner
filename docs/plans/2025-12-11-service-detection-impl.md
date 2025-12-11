# Service Detection and Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect external service dependencies from env vars (postgres, redis, mysql, mongodb), ask user if they want local containers, and generate multi-service docker-compose.yaml with properly wired connections.

**Architecture:** A new service detection agent analyzes collected env vars and groups them semantically by service. The workflow prompts the user once per detected service. Confirmed services are stored in `Analysis.services` and used by the compose agent to generate multi-container setup with proper env var mappings.

**Tech Stack:** Pydantic AI agents, Pydantic models, Typer CLI with Rich prompts, existing workflow graph.

---

## Task 1: Add ServiceConfig Model

**Files:**
- Modify: `src/wunderunner/models/analysis.py:30-58`
- Test: `tests/test_models_analysis.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_models_analysis.py`:

```python
"""Tests for analysis models."""

from wunderunner.models.analysis import Analysis, ServiceConfig, ProjectStructure, BuildStrategy, CodeStyle


def test_service_config_creation():
    """ServiceConfig can be created with type and env_vars."""
    config = ServiceConfig(
        type="postgres",
        env_vars=["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"],
    )
    assert config.type == "postgres"
    assert config.env_vars == ["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"]


def test_analysis_with_services():
    """Analysis model includes services field."""
    analysis = Analysis(
        project_structure=ProjectStructure(runtime="node"),
        build_strategy=BuildStrategy(),
        code_style=CodeStyle(),
        services=[
            ServiceConfig(type="postgres", env_vars=["DATABASE_URL"]),
            ServiceConfig(type="redis", env_vars=["REDIS_URL"]),
        ],
    )
    assert len(analysis.services) == 2
    assert analysis.services[0].type == "postgres"
    assert analysis.services[1].type == "redis"


def test_analysis_services_defaults_to_empty():
    """Analysis.services defaults to empty list."""
    analysis = Analysis(
        project_structure=ProjectStructure(runtime="node"),
        build_strategy=BuildStrategy(),
        code_style=CodeStyle(),
    )
    assert analysis.services == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_analysis.py -v`
Expected: FAIL with "cannot import name 'ServiceConfig'"

**Step 3: Write minimal implementation**

Edit `src/wunderunner/models/analysis.py` - add after `EnvVar` class (around line 38):

```python
class ServiceConfig(BaseModel):
    """A service to create in docker-compose."""

    type: str  # "postgres", "redis", "mysql", "mongodb"
    env_vars: list[str]  # Names of env vars this service satisfies
```

Then modify `Analysis` class to add services field:

```python
class Analysis(BaseModel):
    """Combined result of all analysis passes."""

    project_structure: ProjectStructure
    build_strategy: BuildStrategy
    env_vars: list[EnvVar] = []
    code_style: CodeStyle
    services: list[ServiceConfig] = []  # NEW: confirmed services to create
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_analysis.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/models/analysis.py tests/test_models_analysis.py
git commit -m "feat: add ServiceConfig model for service orchestration"
```

---

## Task 2: Add DetectedService Model for Agent Output

**Files:**
- Modify: `src/wunderunner/models/analysis.py`
- Test: `tests/test_models_analysis.py`

**Step 1: Write the failing test**

Add to `tests/test_models_analysis.py`:

```python
from wunderunner.models.analysis import DetectedService


def test_detected_service_creation():
    """DetectedService captures agent's service detection."""
    detected = DetectedService(
        type="postgres",
        env_vars=["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"],
        confidence=0.95,
    )
    assert detected.type == "postgres"
    assert detected.confidence == 0.95


def test_detected_service_confidence_bounds():
    """DetectedService confidence must be 0-1."""
    detected = DetectedService(
        type="redis",
        env_vars=["REDIS_URL"],
        confidence=0.5,
    )
    assert 0 <= detected.confidence <= 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_analysis.py::test_detected_service_creation -v`
Expected: FAIL with "cannot import name 'DetectedService'"

**Step 3: Write minimal implementation**

Add to `src/wunderunner/models/analysis.py` after `ServiceConfig`:

```python
class DetectedService(BaseModel):
    """A service detected from env vars by the detection agent."""

    type: str  # "postgres", "redis", "mysql", "mongodb"
    env_vars: list[str]  # Which env vars belong to this service
    confidence: float  # 0-1, how confident the grouping is
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_analysis.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/models/analysis.py tests/test_models_analysis.py
git commit -m "feat: add DetectedService model for agent output"
```

---

## Task 3: Create Service Detection Agent

**Files:**
- Create: `src/wunderunner/agents/analysis/services.py`
- Modify: `src/wunderunner/agents/analysis/__init__.py`
- Test: `tests/test_service_detection_agent.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_service_detection_agent.py`:

```python
"""Tests for service detection agent."""

import pytest

from wunderunner.models.analysis import EnvVar, DetectedService


def test_service_detection_prompt_exists():
    """Service detection agent has required prompt constants."""
    from wunderunner.agents.analysis import services

    assert hasattr(services, "USER_PROMPT")
    assert hasattr(services, "SYSTEM_PROMPT")
    assert hasattr(services, "agent")


def test_service_detection_agent_output_type():
    """Service detection agent returns list of DetectedService."""
    from wunderunner.agents.analysis import services

    # The agent's output type should be list[DetectedService]
    assert services.agent._output_type == list[DetectedService]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service_detection_agent.py -v`
Expected: FAIL with "cannot import name 'services'"

**Step 3: Write minimal implementation**

Create `src/wunderunner/agents/analysis/services.py`:

```python
"""Service detection agent - identifies external services from env vars."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.models.analysis import DetectedService
from wunderunner.settings import Analysis, get_model

USER_PROMPT = Template("""\
<env_vars>
{% for var in env_vars %}
- {{ var.name }}{% if var.secret %} (secret){% endif %}{% if var.service %} [{{ var.service }}]{% endif %}

{% endfor %}
</env_vars>

Analyze these environment variables and identify which external services they imply.
Group related variables by service.
""")

SYSTEM_PROMPT = """\
<task>
Analyze environment variables and identify external services they imply.
Group related variables by service and return a list of DetectedService objects.
</task>

<supported_services>
Only detect these services:
- postgres: Database (DATABASE_*, DB_*, POSTGRES_*, PG_*)
- mysql: Database (MYSQL_*, DB_* when MySQL is implied)
- redis: Cache/queue (REDIS_*, CACHE_*)
- mongodb: Document store (MONGO_*, MONGODB_*)
</supported_services>

<grouping_rules>
Use semantic reasoning to group variables:
- DATABASE_HOST, DATABASE_USER, DATABASE_PASS, DATABASE_PORT → postgres (one service)
- DB_CONNECTION_STRING → postgres or mysql (infer from context)
- REDIS_URL alone → redis
- Multiple MONGO_* vars → mongodb (one service)

Do NOT create multiple services for the same database.
Do NOT detect services outside the supported list.
</grouping_rules>

<confidence_scoring>
- 1.0: Explicit service name (POSTGRES_*, REDIS_URL, MONGODB_URI)
- 0.8: Strong pattern match (DATABASE_URL typically postgres)
- 0.6: Reasonable inference (DB_HOST + DB_USER + DB_PASS)
- 0.4: Weak inference (ambiguous patterns)
</confidence_scoring>

<output>
Return list of DetectedService:
- type: Service type ("postgres", "mysql", "redis", "mongodb")
- env_vars: List of variable names that belong to this service
- confidence: 0-1 confidence score
</output>
"""

agent = Agent(
    model=get_model(Analysis.ENV_VARS),  # Reuse env vars model config
    output_type=list[DetectedService],
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
```

Update `src/wunderunner/agents/analysis/__init__.py`:

```python
"""Analysis agents."""

from wunderunner.agents.analysis import (
    build_strategy,
    code_style,
    env_vars,
    project_structure,
    secrets,
    services,  # NEW
)

__all__ = [
    "build_strategy",
    "code_style",
    "env_vars",
    "project_structure",
    "secrets",
    "services",  # NEW
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_service_detection_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/agents/analysis/services.py src/wunderunner/agents/analysis/__init__.py tests/test_service_detection_agent.py
git commit -m "feat: add service detection agent"
```

---

## Task 4: Add Service Prompt Callback to State

**Files:**
- Modify: `src/wunderunner/workflows/state.py:31-49`
- Test: `tests/test_workflow_state.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_workflow_state.py`:

```python
"""Tests for workflow state."""

from pathlib import Path

from wunderunner.workflows.state import ContainerizeState, ServicePromptCallback


def test_service_prompt_callback_type():
    """ServicePromptCallback has correct signature."""
    # Callback takes (service_type, env_vars) and returns bool
    def mock_callback(service_type: str, env_vars: list[str]) -> bool:
        return True

    # Should be assignable to the type
    callback: ServicePromptCallback = mock_callback
    assert callback("postgres", ["DB_HOST"]) is True


def test_state_has_service_prompt_callback():
    """ContainerizeState has on_service_prompt field."""
    state = ContainerizeState(path=Path("/tmp"))
    assert hasattr(state, "on_service_prompt")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow_state.py -v`
Expected: FAIL with "cannot import name 'ServicePromptCallback'"

**Step 3: Write minimal implementation**

Edit `src/wunderunner/workflows/state.py`:

After line 34, add the new callback type:

```python
ServicePromptCallback = Callable[[str, list[str]], bool]  # (service_type, env_vars) -> confirm
```

Add a default implementation after `_noop_hint_prompt`:

```python
def _noop_service_prompt(service_type: str, env_vars: list[str]) -> bool:
    """Default service prompt - auto-confirms all services."""
    return True
```

Add to `ContainerizeState` class after `on_hint_prompt`:

```python
    on_service_prompt: ServicePromptCallback = _noop_service_prompt
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/workflows/state.py tests/test_workflow_state.py
git commit -m "feat: add service prompt callback to workflow state"
```

---

## Task 5: Create Service Detection Activity

**Files:**
- Create: `src/wunderunner/activities/service_detection.py`
- Test: `tests/test_activities_service_detection.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_activities_service_detection.py`:

```python
"""Tests for service detection activity."""

import pytest

from wunderunner.models.analysis import EnvVar


def test_detect_services_function_exists():
    """detect_services function exists and is importable."""
    from wunderunner.activities.service_detection import detect_services

    assert callable(detect_services)


def test_confirm_services_function_exists():
    """confirm_services function exists."""
    from wunderunner.activities.service_detection import confirm_services

    assert callable(confirm_services)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_activities_service_detection.py -v`
Expected: FAIL with "No module named 'wunderunner.activities.service_detection'"

**Step 3: Write minimal implementation**

Create `src/wunderunner/activities/service_detection.py`:

```python
"""Service detection activity."""

import logging

from wunderunner.agents.analysis import services as services_agent
from wunderunner.models.analysis import DetectedService, EnvVar, ServiceConfig
from wunderunner.settings import Analysis as AnalysisAgent
from wunderunner.settings import get_fallback_model
from wunderunner.workflows.state import ServicePromptCallback

logger = logging.getLogger(__name__)


async def detect_services(env_vars: list[EnvVar]) -> list[DetectedService]:
    """Detect external services from environment variables.

    Args:
        env_vars: Combined list of env vars and secrets from analysis.

    Returns:
        List of detected services with their associated env vars.
    """
    if not env_vars:
        return []

    prompt = services_agent.USER_PROMPT.render(env_vars=env_vars)

    try:
        result = await services_agent.agent.run(
            prompt,
            model=get_fallback_model(AnalysisAgent.ENV_VARS),
        )
        return result.output
    except Exception as e:
        logger.warning("Service detection failed: %s", e)
        return []


def confirm_services(
    detected: list[DetectedService],
    prompt_callback: ServicePromptCallback,
) -> list[ServiceConfig]:
    """Prompt user to confirm which detected services to create.

    Args:
        detected: Services detected by the agent.
        prompt_callback: Callback to prompt user (service_type, env_vars) -> bool.

    Returns:
        List of confirmed ServiceConfig objects.
    """
    confirmed = []
    for service in detected:
        if prompt_callback(service.type, service.env_vars):
            confirmed.append(
                ServiceConfig(type=service.type, env_vars=service.env_vars)
            )
    return confirmed
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_activities_service_detection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/activities/service_detection.py tests/test_activities_service_detection.py
git commit -m "feat: add service detection activity"
```

---

## Task 6: Add Service Templates for Compose Generation

**Files:**
- Create: `src/wunderunner/templates/services.py`
- Test: `tests/test_service_templates.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_service_templates.py`:

```python
"""Tests for service templates."""

import pytest


def test_service_templates_exist():
    """SERVICE_TEMPLATES dict exists with expected services."""
    from wunderunner.templates.services import SERVICE_TEMPLATES

    assert "postgres" in SERVICE_TEMPLATES
    assert "redis" in SERVICE_TEMPLATES
    assert "mysql" in SERVICE_TEMPLATES
    assert "mongodb" in SERVICE_TEMPLATES


def test_postgres_template():
    """Postgres template has required fields."""
    from wunderunner.templates.services import SERVICE_TEMPLATES

    postgres = SERVICE_TEMPLATES["postgres"]
    assert "image" in postgres
    assert "postgres" in postgres["image"]
    assert "environment" in postgres
    assert "POSTGRES_USER" in postgres["environment"]
    assert "POSTGRES_PASSWORD" in postgres["environment"]


def test_env_mappings_exist():
    """ENV_MAPPINGS dict exists for wiring app to services."""
    from wunderunner.templates.services import ENV_MAPPINGS

    assert "postgres" in ENV_MAPPINGS
    assert "redis" in ENV_MAPPINGS


def test_get_env_value_for_service():
    """get_env_value returns correct value for env var pattern."""
    from wunderunner.templates.services import get_env_value

    # Exact matches
    assert get_env_value("postgres", "DATABASE_HOST") == "postgres"
    assert get_env_value("postgres", "DATABASE_USER") == "postgres"
    assert get_env_value("postgres", "DATABASE_PORT") == "5432"

    # URL patterns
    assert "postgres://" in get_env_value("postgres", "DATABASE_URL")

    # Redis
    assert get_env_value("redis", "REDIS_URL") == "redis://redis:6379"
    assert get_env_value("redis", "REDIS_HOST") == "redis"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service_templates.py -v`
Expected: FAIL with "No module named 'wunderunner.templates'"

**Step 3: Write minimal implementation**

Create `src/wunderunner/templates/__init__.py`:

```python
"""Templates for generation."""
```

Create `src/wunderunner/templates/services.py`:

```python
"""Service container templates and env var mappings."""

SERVICE_TEMPLATES: dict[str, dict] = {
    "postgres": {
        "image": "postgres:16-alpine",
        "environment": {
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": "app",
        },
        "ports": ["5432:5432"],
    },
    "redis": {
        "image": "redis:7-alpine",
        "ports": ["6379:6379"],
    },
    "mysql": {
        "image": "mysql:8",
        "environment": {
            "MYSQL_ROOT_PASSWORD": "root",
            "MYSQL_DATABASE": "app",
            "MYSQL_USER": "app",
            "MYSQL_PASSWORD": "app",
        },
        "ports": ["3306:3306"],
    },
    "mongodb": {
        "image": "mongo:7",
        "ports": ["27017:27017"],
    },
}

# Patterns for mapping app env vars to service values
# Keys are suffixes/patterns, values are the actual values
ENV_MAPPINGS: dict[str, dict[str, str]] = {
    "postgres": {
        "_HOST": "postgres",
        "_USER": "postgres",
        "_PASS": "postgres",
        "_PASSWORD": "postgres",
        "_DB": "app",
        "_DATABASE": "app",
        "_PORT": "5432",
        "_URL": "postgres://postgres:postgres@postgres:5432/app",
    },
    "mysql": {
        "_HOST": "mysql",
        "_USER": "app",
        "_PASS": "app",
        "_PASSWORD": "app",
        "_DB": "app",
        "_DATABASE": "app",
        "_PORT": "3306",
        "_URL": "mysql://app:app@mysql:3306/app",
    },
    "redis": {
        "_HOST": "redis",
        "_PORT": "6379",
        "_URL": "redis://redis:6379",
    },
    "mongodb": {
        "_HOST": "mongodb",
        "_PORT": "27017",
        "_URL": "mongodb://mongodb:27017/app",
        "_URI": "mongodb://mongodb:27017/app",
    },
}


def get_env_value(service_type: str, env_var_name: str) -> str:
    """Get the value for an env var based on service type.

    Args:
        service_type: The service type (postgres, redis, etc.)
        env_var_name: The env var name (DATABASE_HOST, REDIS_URL, etc.)

    Returns:
        The value to use for this env var when connecting to the service.
    """
    mappings = ENV_MAPPINGS.get(service_type, {})

    # Check each suffix pattern
    for suffix, value in mappings.items():
        if env_var_name.upper().endswith(suffix):
            return value

    # Default to service name (works for HOST-like vars)
    return service_type
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_service_templates.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/templates/__init__.py src/wunderunner/templates/services.py tests/test_service_templates.py
git commit -m "feat: add service templates and env var mappings"
```

---

## Task 7: Update Compose Agent to Support Services

**Files:**
- Modify: `src/wunderunner/agents/generation/compose.py`
- Test: `tests/test_compose_with_services.py` (new file)

**Step 1: Write the failing test**

Create `tests/test_compose_with_services.py`:

```python
"""Tests for compose generation with services."""

import pytest


def test_compose_prompt_includes_services():
    """Compose USER_PROMPT template accepts services parameter."""
    from wunderunner.agents.generation.compose import USER_PROMPT

    # Should render without error when services provided
    rendered = USER_PROMPT.render(
        analysis={"project_structure": {"runtime": "node", "port": 3000}},
        dockerfile="FROM node:20",
        secrets=[],
        learnings=[],
        hints=[],
        existing_compose=None,
        services=[{"type": "postgres", "env_vars": ["DATABASE_URL"]}],
    )

    assert "postgres" in rendered


def test_compose_system_prompt_mentions_services():
    """Compose SYSTEM_PROMPT includes guidance for services."""
    from wunderunner.agents.generation.compose import SYSTEM_PROMPT

    assert "services" in SYSTEM_PROMPT.lower()
    # Should mention depends_on for service ordering
    assert "depends_on" in SYSTEM_PROMPT
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_compose_with_services.py -v`
Expected: FAIL (template doesn't accept services parameter yet)

**Step 3: Write minimal implementation**

Update `src/wunderunner/agents/generation/compose.py`:

Replace the existing `USER_PROMPT`:

```python
USER_PROMPT = Template("""\
<project>
Runtime: {{ analysis.project_structure.runtime }}
Framework: {{ analysis.project_structure.framework or 'none' }}
Port: {{ analysis.project_structure.port or 3000 }}
</project>

<dockerfile>
{{ dockerfile }}
</dockerfile>

{% if services %}
<services_to_create>
Create these service containers alongside the app:
{% for svc in services %}
- {{ svc.type }}: wire env vars {{ svc.env_vars | join(', ') }}
{% endfor %}
</services_to_create>
{% endif %}

{% if learnings %}
<previous_errors>
{% for learning in learnings %}
- [{{ learning.phase }}] {{ learning.error_message }}
{% endfor %}
</previous_errors>
{% endif %}

{% if existing_compose %}
<current_compose>
{{ existing_compose }}
</current_compose>
Fix the errors and return improved docker-compose.yaml.
{% else %}
Generate a docker-compose.yaml for this project.
{% endif %}
""")
```

Replace the existing `SYSTEM_PROMPT`:

```python
SYSTEM_PROMPT = """\
Generate a docker-compose.yaml file.

RULES:
1. Start with "services:" (no version declaration needed)
2. Match the port from the Dockerfile's EXPOSE
3. Use "build: ." to build from the Dockerfile
4. NEVER add volumes - no volumes section, no volume mounts
5. Do NOT add health checks unless the app has a /health endpoint

SERVICE CONTAINERS:
If <services_to_create> is provided, add those containers using these templates:

postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    POSTGRES_DB: app
  ports:
    - "5432:5432"

redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"

mysql:
  image: mysql:8
  environment:
    MYSQL_ROOT_PASSWORD: root
    MYSQL_DATABASE: app
  ports:
    - "3306:3306"

mongodb:
  image: mongo:7
  ports:
    - "27017:27017"

WIRING ENV VARS:
For each service, add environment variables to the app container:
- *_HOST vars → service name (e.g., DATABASE_HOST: postgres)
- *_USER vars → "postgres" for postgres, "app" for mysql
- *_PASS/*_PASSWORD vars → "postgres" for postgres, "app" for mysql
- *_PORT vars → service port (5432, 6379, 3306, 27017)
- *_URL vars → full connection URL (e.g., postgres://postgres:postgres@postgres:5432/app)

APP ORDERING:
When services exist, add depends_on to the app:
  app:
    depends_on:
      - postgres
      - redis

NEVER add volumes. Volumes cause mount conflicts with Dockerfile operations.
"""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_compose_with_services.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/agents/generation/compose.py tests/test_compose_with_services.py
git commit -m "feat: update compose agent to support service containers"
```

---

## Task 8: Update Services Activity to Pass Services

**Files:**
- Modify: `src/wunderunner/activities/services.py:26-69`
- Test: Update existing tests or add new ones

**Step 1: Write the failing test**

Add to a test file (or create `tests/test_services_activity.py`):

```python
"""Tests for services activity."""

import pytest
from unittest.mock import AsyncMock, patch

from wunderunner.models.analysis import ServiceConfig


def test_generate_accepts_services_param():
    """services.generate accepts services parameter."""
    from wunderunner.activities import services
    import inspect

    sig = inspect.signature(services.generate)
    params = list(sig.parameters.keys())
    assert "services" in params
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services_activity.py -v`
Expected: FAIL ("services" not in params)

**Step 3: Write minimal implementation**

Update `src/wunderunner/activities/services.py`:

Modify the `generate` function signature and implementation:

```python
async def generate(
    analysis: Analysis,
    dockerfile_content: str,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
    project_path: Path | None = None,
    services: list[ServiceConfig] | None = None,  # NEW
) -> str:
    """Generate or refine docker-compose.yaml based on analysis and learnings.

    Args:
        analysis: Project analysis result.
        dockerfile_content: The Dockerfile being used.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this compose file instead of generating fresh.
        project_path: Path to project directory (for tool access).
        services: List of confirmed services to create containers for.

    Returns:
        docker-compose.yaml content as string.

    Raises:
        ServicesError: If generation/refinement fails.
    """
    # Extract secrets from analysis
    secrets = [v for v in analysis.env_vars if v.secret]

    # Convert services to dict format for template
    services_data = None
    if services:
        services_data = [{"type": s.type, "env_vars": s.env_vars} for s in services]

    prompt = compose_agent.USER_PROMPT.render(
        analysis=analysis.model_dump(),
        dockerfile=dockerfile_content,
        secrets=secrets,
        learnings=learnings,
        hints=hints,
        existing_compose=existing,
        services=services_data,  # NEW
    )

    try:
        result = await compose_agent.agent.run(
            prompt,
            model=get_fallback_model(Generation.COMPOSE),
        )
        return result.output.compose_yaml
    except Exception as e:
        raise ServicesError(f"Failed to generate docker-compose.yaml: {e}") from e
```

Add the import at the top:

```python
from wunderunner.models.analysis import Analysis, ServiceConfig
```

(Replace the existing `Analysis` import if it's imported from somewhere else)

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services_activity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/activities/services.py tests/test_services_activity.py
git commit -m "feat: update services activity to pass services to compose"
```

---

## Task 9: Add DetectServices Node to Workflow

**Files:**
- Modify: `src/wunderunner/workflows/containerize.py`
- Test: Manual verification (workflow integration)

**Step 1: Understand the change**

We need to add a new `DetectServices` node that:
1. Runs after `Analyze` (or after `CollectSecrets` if secrets exist)
2. Calls the service detection activity
3. Prompts user for each detected service
4. Stores confirmed services in `analysis.services`
5. Then proceeds to `Dockerfile`

**Step 2: Write the implementation**

Update `src/wunderunner/workflows/containerize.py`:

Add import at top:

```python
from wunderunner.activities import service_detection
```

Add the new node after `CollectSecrets`:

```python
@dataclass
class DetectServices(BaseNode[ContainerizeState]):
    """Detect and prompt for external service containers."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        progress = ctx.state.on_progress
        service_prompt = ctx.state.on_service_prompt

        # Detect services from all env vars
        all_env_vars = ctx.state.analysis.env_vars
        detected = await service_detection.detect_services(all_env_vars)

        if not detected:
            return Dockerfile()

        progress(Severity.INFO, f"Detected {len(detected)} service dependency(ies)")

        # Prompt user for each service
        confirmed = service_detection.confirm_services(detected, service_prompt)

        if confirmed:
            ctx.state.analysis.services = confirmed
            progress(Severity.SUCCESS, f"Will create {len(confirmed)} service container(s)")

        return Dockerfile()
```

Modify `Analyze` node to route to `DetectServices`:

```python
@dataclass
class Analyze(BaseNode[ContainerizeState]):
    """Run analysis agents and check for secrets."""

    async def run(self, ctx: Ctx) -> CollectSecrets | DetectServices:  # CHANGED
        progress = ctx.state.on_progress
        progress(Severity.INFO, "Analyzing project...")
        analysis = await project.analyze(ctx.state.path, ctx.state.rebuild)
        ctx.state.analysis = analysis

        runtime = analysis.project_structure.runtime
        framework = analysis.project_structure.framework or "no framework"
        progress(Severity.SUCCESS, f"Detected {runtime} ({framework})")

        secrets = [v for v in analysis.env_vars if v.secret]
        if secrets:
            return CollectSecrets()
        return DetectServices()  # CHANGED: go to service detection
```

Modify `CollectSecrets` to route to `DetectServices`:

```python
@dataclass
class CollectSecrets(BaseNode[ContainerizeState]):
    """Prompt user for secret values via callback."""

    async def run(self, ctx: Ctx) -> DetectServices:  # CHANGED
        progress = ctx.state.on_progress
        secret_prompt = ctx.state.on_secret_prompt
        secrets = [v for v in ctx.state.analysis.env_vars if v.secret]

        progress(Severity.INFO, f"Collecting {len(secrets)} secret(s)...")
        for var in secrets:
            value = secret_prompt(var.name, var.service)
            ctx.state.secret_values[var.name] = value

        progress(Severity.SUCCESS, "Secrets collected")
        return DetectServices()  # CHANGED
```

Update the graph nodes list:

```python
containerize_graph = Graph(
    nodes=[
        Analyze,
        CollectSecrets,
        DetectServices,  # NEW
        Dockerfile,
        Validate,
        Services,
        Build,
        Start,
        Healthcheck,
        RetryOrHint,
        HumanHint,
        ImproveDockerfile,
    ],
    state_type=ContainerizeState,
    run_end_type=Success,
)
```

**Step 3: Run lint to verify syntax**

Run: `make lint`
Expected: All checks passed

**Step 4: Commit**

```bash
git add src/wunderunner/workflows/containerize.py
git commit -m "feat: add DetectServices node to workflow"
```

---

## Task 10: Update Services Node to Use analysis.services

**Files:**
- Modify: `src/wunderunner/workflows/containerize.py:163-198`

**Step 1: Write the implementation**

Update the `Services` node to pass `analysis.services` to the generate function:

```python
@dataclass
class Services(BaseNode[ContainerizeState]):
    """Generate or refine docker-compose.yaml."""

    async def run(self, ctx: Ctx) -> Build | RetryOrHint:
        progress = ctx.state.on_progress
        is_refine = ctx.state.compose_content is not None
        action = "Refining" if is_refine else "Generating"

        try:
            progress(Severity.INFO, f"{action} docker-compose.yaml...")
            ctx.state.compose_content = await services.generate(
                ctx.state.analysis,
                ctx.state.dockerfile_content,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.compose_content,
                project_path=ctx.state.path,
                services=ctx.state.analysis.services,  # NEW: pass confirmed services
            )

            compose_path = ctx.state.path / "docker-compose.yaml"
            async with aiofiles.open(compose_path, "w") as f:
                await f.write(ctx.state.compose_content)

            progress(Severity.SUCCESS, f"docker-compose.yaml {action.lower()[:-3]}ed")
            return Build()
        except ServicesError as e:
            progress(Severity.ERROR, "Compose generation failed")
            learning = Learning(
                phase=Phase.SERVICES,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)
```

**Step 2: Run lint to verify syntax**

Run: `make lint`
Expected: All checks passed

**Step 3: Commit**

```bash
git add src/wunderunner/workflows/containerize.py
git commit -m "feat: pass confirmed services to compose generation"
```

---

## Task 11: Add Rich Service Prompt to CLI

**Files:**
- Modify: `src/wunderunner/cli/main.py:103-127`

**Step 1: Write the implementation**

Add a new callback factory function after `_make_hint_prompt_callback`:

```python
def _make_service_prompt_callback(console: Console):
    """Create a Rich-based service prompt callback."""

    # Emoji/icon for each service type
    service_icons = {
        "postgres": "\U0001F418",  # elephant
        "mysql": "\U0001F42C",     # dolphin
        "redis": "\U0001F534",     # red circle
        "mongodb": "\U0001F343",   # leaf
    }

    def callback(service_type: str, env_vars: list[str]) -> bool:
        icon = service_icons.get(service_type, "\U0001F4E6")  # package
        var_list = ", ".join(env_vars[:3])
        if len(env_vars) > 3:
            var_list += f" +{len(env_vars) - 3} more"

        console.print(f"\n{icon} [bold]Detected {service_type}[/bold] dependency")
        console.print(f"   [dim]Variables: {var_list}[/dim]")

        response = Prompt.ask(
            f"   Add a {service_type} container?",
            choices=["y", "n"],
            default="y",
            console=console,
        )
        return response.lower() == "y"

    return callback
```

Update the `init` command to use the new callback (around line 165-171):

```python
    state = ContainerizeState(
        path=project_path,
        rebuild=rebuild,
        on_progress=_make_progress_callback(console),
        on_secret_prompt=_make_secret_prompt_callback(console),
        on_hint_prompt=_make_hint_prompt_callback(console),
        on_service_prompt=_make_service_prompt_callback(console),  # NEW
    )
```

**Step 2: Run lint to verify syntax**

Run: `make lint`
Expected: All checks passed

**Step 3: Commit**

```bash
git add src/wunderunner/cli/main.py
git commit -m "feat: add Rich service prompt to CLI"
```

---

## Task 12: Run Full Integration Test

**Step 1: Run all tests**

Run: `make test`
Expected: All tests pass

**Step 2: Run lint**

Run: `make lint`
Expected: All checks passed

**Step 3: Manual test with a real project**

Find or create a simple Node.js project with DATABASE_URL:

```bash
# Create test project
mkdir -p /tmp/test-service-detection
cd /tmp/test-service-detection
echo '{"name": "test", "scripts": {"dev": "node index.js"}}' > package.json
echo 'console.log(process.env.DATABASE_URL)' > index.js
echo 'DATABASE_URL=postgres://localhost/test' > .env.example
```

Run wunderunner:

```bash
cd /path/to/wunderunner
uv run wxr /tmp/test-service-detection
```

Expected: Should prompt "Detected postgres dependency... Add a postgres container? [Y/n]"

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete service detection and orchestration feature"
```

---

## Summary

This plan implements service detection and orchestration in 12 tasks:

1. **Task 1-2**: Add data models (`ServiceConfig`, `DetectedService`)
2. **Task 3**: Create service detection agent
3. **Task 4**: Add service prompt callback to state
4. **Task 5**: Create service detection activity
5. **Task 6**: Add service templates and env mappings
6. **Task 7-8**: Update compose agent and activity
7. **Task 9-10**: Add workflow node and routing
8. **Task 11**: Add CLI prompt
9. **Task 12**: Integration testing

Each task follows TDD: write failing test, implement, verify, commit.

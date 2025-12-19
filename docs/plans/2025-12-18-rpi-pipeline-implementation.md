# RESEARCH-PLAN-IMPLEMENT Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the verification loop backbone with a three-phase pipeline (RESEARCH → PLAN → IMPLEMENT) that uses file-based artifact handoff and fresh LLM context per phase.

**Architecture:** Parallel specialist subagents produce structured findings, synthesized into `research.md`. A plan agent generates exact file contents in `plan.md`. Implement phase writes files and runs verification. Errors trigger ERROR-RESEARCH → FIX-PLAN cycle with constraint tracking in `fixes.json`.

**Tech Stack:**
- Pydantic AI agents with `defer_model_check=True`
- Pydantic v2 models for structured data
- `asyncio.gather()` for parallel specialist execution
- Markdown artifacts on disk (`.wunderunner/`)
- Existing filesystem tools from `wunderunner.agents.tools`

**Design Document:** `docs/plans/2025-12-18-research-plan-implement-design.md`

---

## File Structure (New)

```
src/wunderunner/
├── pipeline/                    # NEW: RPI pipeline module
│   ├── __init__.py
│   ├── models.py               # Artifact models (ResearchFindings, Plan, Fix, etc.)
│   ├── artifacts.py            # Read/write markdown artifacts
│   ├── research/               # RESEARCH phase
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Spawns specialists, synthesizes
│   │   ├── specialists/        # Individual specialist agents
│   │   │   ├── __init__.py
│   │   │   ├── runtime.py
│   │   │   ├── dependencies.py
│   │   │   ├── config.py
│   │   │   └── services.py
│   │   └── synthesis.py        # Combine specialist outputs → research.md
│   ├── plan/                   # PLAN phase
│   │   ├── __init__.py
│   │   └── agent.py            # Generate exact Dockerfile/compose
│   ├── implement/              # IMPLEMENT phase
│   │   ├── __init__.py
│   │   ├── executor.py         # Parse plan, write files
│   │   └── verify.py           # Run docker build/start/healthcheck
│   ├── errors/                 # Error handling
│   │   ├── __init__.py
│   │   ├── research.py         # ERROR-RESEARCH agent
│   │   ├── fix_plan.py         # FIX-PLAN agent
│   │   └── constraints.py      # Constraint management
│   └── runner.py               # Main pipeline orchestrator
```

## Implementation Order

1. **Models** (Part 1) — Define all Pydantic models for artifacts
2. **Research Phase** (Part 2) — Specialists + orchestrator + synthesis
3. **Plan Phase** (Part 3) — Plan generation agent
4. **Implement Phase** (Part 4) — File writing + verification
5. **Error Handling** (Part 5) — ERROR-RESEARCH, FIX-PLAN, constraints
6. **CLI Integration** (Part 6) — Wire up with feature flag

---

## Testing Strategy

- Unit tests for each specialist agent (mock filesystem)
- Unit tests for artifact parsing/writing
- Integration tests for full pipeline (mock LLM responses)
- Use existing fixtures from `conftest.py` where applicable
- Follow TDD: write failing test → implement → verify pass → commit

## Key Patterns from Existing Codebase

**Agent creation pattern** (from `agents/analysis/project_structure.py`):
```python
agent = Agent(
    model=get_model(AgentType.ENUM_VALUE),
    output_type=OutputModel,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
register_tools(agent)
```

**Async file I/O** (from `storage/context.py`):
```python
async with aiofiles.open(path) as f:
    content = await f.read()
return Model.model_validate_json(content)
```

**Test fixtures** (from `conftest.py`):
```python
@pytest.fixture
def node_analysis() -> Analysis:
    return Analysis(...)
```
## Part 1: Models for Artifacts

All artifact models live in `src/wunderunner/pipeline/models.py`. These define the structured data that flows between phases.

---

### Task 1.1: Create pipeline module structure

**Files:**
- Create: `src/wunderunner/pipeline/__init__.py`
- Create: `src/wunderunner/pipeline/models.py`
- Test: `tests/test_pipeline_models.py`

**Step 1: Write the failing test for RuntimeFindings**

```python
# tests/test_pipeline_models.py
"""Tests for pipeline artifact models."""

import pytest
from wunderunner.pipeline.models import RuntimeFindings


def test_runtime_findings_required_fields():
    """RuntimeFindings requires language."""
    findings = RuntimeFindings(language="python")
    assert findings.language == "python"
    assert findings.version is None
    assert findings.framework is None


def test_runtime_findings_all_fields():
    """RuntimeFindings accepts all fields."""
    findings = RuntimeFindings(
        language="python",
        version="3.11",
        framework="fastapi",
        entrypoint="src/main.py",
    )
    assert findings.language == "python"
    assert findings.version == "3.11"
    assert findings.framework == "fastapi"
    assert findings.entrypoint == "src/main.py"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_runtime_findings_required_fields -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'wunderunner.pipeline'"

**Step 3: Create module structure and RuntimeFindings model**

```python
# src/wunderunner/pipeline/__init__.py
"""RESEARCH-PLAN-IMPLEMENT pipeline module."""
```

```python
# src/wunderunner/pipeline/models.py
"""Pydantic models for pipeline artifacts."""

from pydantic import BaseModel, Field


class RuntimeFindings(BaseModel):
    """Output from runtime-detector specialist."""

    language: str = Field(description="Runtime language: python, node, go, rust")
    version: str | None = Field(default=None, description="Version string: 3.11, 20, 1.21")
    framework: str | None = Field(default=None, description="Web framework: fastapi, express, gin")
    entrypoint: str | None = Field(default=None, description="Main file path: src/main.py")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_runtime_findings_required_fields tests/test_pipeline_models.py::test_runtime_findings_all_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/ tests/test_pipeline_models.py
git commit -m "feat(pipeline): add RuntimeFindings model"
```

---

### Task 1.2: Add DependencyFindings model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import DependencyFindings, NativeDependency


def test_dependency_findings_minimal():
    """DependencyFindings requires package_manager."""
    findings = DependencyFindings(package_manager="pip")
    assert findings.package_manager == "pip"
    assert findings.native_deps == []
    assert findings.build_command is None


def test_dependency_findings_with_native():
    """DependencyFindings tracks native dependencies."""
    findings = DependencyFindings(
        package_manager="pip",
        native_deps=[
            NativeDependency(name="libpq-dev", reason="psycopg2 requires PostgreSQL client"),
        ],
        build_command="pip install -r requirements.txt",
        start_command="uvicorn app:app --host 0.0.0.0",
    )
    assert len(findings.native_deps) == 1
    assert findings.native_deps[0].name == "libpq-dev"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_dependency_findings_minimal -v`
Expected: FAIL with "ImportError: cannot import name 'DependencyFindings'"

**Step 3: Add DependencyFindings model**

```python
# src/wunderunner/pipeline/models.py (append)


class NativeDependency(BaseModel):
    """A native/system dependency required for the build."""

    name: str = Field(description="Package name: libpq-dev, build-essential")
    reason: str = Field(description="Why it's needed: psycopg2 requires PostgreSQL client")


class DependencyFindings(BaseModel):
    """Output from dependency-analyzer specialist."""

    package_manager: str = Field(description="Package manager: pip, uv, npm, yarn, pnpm")
    package_manager_version: str | None = Field(default=None, description="Version: pnpm@9.1.0")
    native_deps: list[NativeDependency] = Field(default_factory=list)
    build_command: str | None = Field(default=None, description="Build command: npm run build")
    start_command: str | None = Field(default=None, description="Start command: npm start")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_dependency_findings_minimal tests/test_pipeline_models.py::test_dependency_findings_with_native -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add DependencyFindings model"
```

---

### Task 1.3: Add ConfigFindings model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ConfigFindings, EnvVarFinding


def test_config_findings_empty():
    """ConfigFindings defaults to empty lists."""
    findings = ConfigFindings()
    assert findings.env_vars == []
    assert findings.config_files == []


def test_config_findings_with_secrets():
    """ConfigFindings tracks env vars with secret flag."""
    findings = ConfigFindings(
        env_vars=[
            EnvVarFinding(name="DATABASE_URL", required=True, secret=True),
            EnvVarFinding(name="PORT", required=False, default="3000"),
        ],
        config_files=[".env.example"],
    )
    assert len(findings.env_vars) == 2
    assert findings.env_vars[0].secret is True
    assert findings.env_vars[1].default == "3000"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_config_findings_empty -v`
Expected: FAIL with "ImportError: cannot import name 'ConfigFindings'"

**Step 3: Add ConfigFindings model**

```python
# src/wunderunner/pipeline/models.py (append)


class EnvVarFinding(BaseModel):
    """An environment variable discovered in the project."""

    name: str = Field(description="Variable name: DATABASE_URL")
    required: bool = Field(default=True, description="Whether the app fails without it")
    secret: bool = Field(default=False, description="Whether it contains sensitive data")
    default: str | None = Field(default=None, description="Default value if any")
    service: str | None = Field(default=None, description="Related service: postgres, redis")


class ConfigFindings(BaseModel):
    """Output from config-finder specialist."""

    env_vars: list[EnvVarFinding] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list, description="Config files found: .env.example")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_config_findings_empty tests/test_pipeline_models.py::test_config_findings_with_secrets -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ConfigFindings model"
```

---

### Task 1.4: Add ServiceFindings model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ServiceFindings, ServiceFinding


def test_service_findings_empty():
    """ServiceFindings defaults to empty list."""
    findings = ServiceFindings()
    assert findings.services == []


def test_service_findings_with_services():
    """ServiceFindings tracks discovered services."""
    findings = ServiceFindings(
        services=[
            ServiceFinding(type="postgres", version="15", env_var="DATABASE_URL"),
            ServiceFinding(type="redis", env_var="REDIS_URL"),
        ]
    )
    assert len(findings.services) == 2
    assert findings.services[0].version == "15"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_service_findings_empty -v`
Expected: FAIL with "ImportError: cannot import name 'ServiceFindings'"

**Step 3: Add ServiceFindings model**

```python
# src/wunderunner/pipeline/models.py (append)


class ServiceFinding(BaseModel):
    """A backing service discovered in the project."""

    type: str = Field(description="Service type: postgres, redis, rabbitmq")
    version: str | None = Field(default=None, description="Version if detected: 15, 7")
    env_var: str | None = Field(default=None, description="Related env var: DATABASE_URL")


class ServiceFindings(BaseModel):
    """Output from service-detector specialist."""

    services: list[ServiceFinding] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_service_findings_empty tests/test_pipeline_models.py::test_service_findings_with_services -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ServiceFindings model"
```

---

### Task 1.5: Add ResearchResult composite model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ResearchResult


def test_research_result_combines_findings():
    """ResearchResult combines all specialist findings."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="python", version="3.11", framework="fastapi"),
        dependencies=DependencyFindings(package_manager="uv", start_command="uvicorn app:app"),
        config=ConfigFindings(env_vars=[EnvVarFinding(name="DATABASE_URL", secret=True)]),
        services=ServiceFindings(services=[ServiceFinding(type="postgres")]),
    )
    assert result.runtime.language == "python"
    assert result.dependencies.package_manager == "uv"
    assert len(result.config.env_vars) == 1
    assert len(result.services.services) == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_research_result_combines_findings -v`
Expected: FAIL with "ImportError: cannot import name 'ResearchResult'"

**Step 3: Add ResearchResult model**

```python
# src/wunderunner/pipeline/models.py (append)


class ResearchResult(BaseModel):
    """Combined output from all RESEARCH phase specialists."""

    runtime: RuntimeFindings
    dependencies: DependencyFindings
    config: ConfigFindings
    services: ServiceFindings
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_research_result_combines_findings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ResearchResult composite model"
```

---

### Task 1.6: Add ContainerizationPlan model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep


def test_containerization_plan_required_fields():
    """ContainerizationPlan requires dockerfile content."""
    plan = ContainerizationPlan(
        summary="Python FastAPI app",
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        verification=[
            VerificationStep(command="docker build -t app .", expected="exit 0"),
        ],
        reasoning="Using slim image for minimal size",
    )
    assert plan.dockerfile.startswith("FROM")
    assert plan.compose is None
    assert len(plan.verification) == 1


def test_containerization_plan_with_compose():
    """ContainerizationPlan can include compose content."""
    plan = ContainerizationPlan(
        summary="Node app with PostgreSQL",
        dockerfile="FROM node:20-slim\n",
        compose="services:\n  app:\n    build: .\n",
        verification=[],
        reasoning="Multi-service setup",
    )
    assert plan.compose is not None
    assert "services:" in plan.compose
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_containerization_plan_required_fields -v`
Expected: FAIL with "ImportError: cannot import name 'ContainerizationPlan'"

**Step 3: Add ContainerizationPlan model**

```python
# src/wunderunner/pipeline/models.py (append)


class VerificationStep(BaseModel):
    """A verification step to run after file generation."""

    command: str = Field(description="Command to run: docker build -t app .")
    expected: str = Field(description="Expected outcome: exit 0, 200 OK")
    phase: str = Field(default="BUILD", description="Phase: BUILD, START, HEALTHCHECK")


class ContainerizationPlan(BaseModel):
    """Output from PLAN phase - exact file contents."""

    summary: str = Field(description="Brief description of the containerization approach")
    dockerfile: str = Field(description="Exact Dockerfile content")
    compose: str | None = Field(default=None, description="Exact docker-compose.yaml content")
    verification: list[VerificationStep] = Field(default_factory=list)
    reasoning: str = Field(description="Why this approach was chosen")
    constraints_honored: list[str] = Field(default_factory=list, description="Constraints from fixes.json")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_containerization_plan_required_fields tests/test_pipeline_models.py::test_containerization_plan_with_compose -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ContainerizationPlan model"
```

---

### Task 1.7: Add FixAttempt and FixHistory models

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from datetime import datetime, UTC
from wunderunner.pipeline.models import (
    FixAttempt,
    FixHistory,
    FixChange,
    FixError,
    Constraint,
    ConstraintStatus,
)


def test_fix_attempt_records_change():
    """FixAttempt records what was tried and outcome."""
    attempt = FixAttempt(
        attempt=1,
        phase="BUILD",
        error=FixError(type="missing_dependency", message="No module named 'pandas'"),
        diagnosis="pandas not in requirements",
        changes=[
            FixChange(
                file="Dockerfile",
                before="RUN pip install -r requirements.txt",
                after="RUN pip install -r requirements.txt pandas",
            )
        ],
        outcome="success",
    )
    assert attempt.outcome == "success"
    assert len(attempt.changes) == 1


def test_fix_history_manages_constraints():
    """FixHistory tracks attempts and derives constraints."""
    history = FixHistory(project="my-app")
    assert history.attempts == []
    assert history.active_constraints == []


def test_constraint_lifecycle():
    """Constraints start hard, become soft after successes."""
    constraint = Constraint(
        id="c1",
        rule="MUST include pandas",
        reason="Required import",
        from_attempt=1,
    )
    assert constraint.status == ConstraintStatus.HARD
    assert constraint.success_count == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_fix_attempt_records_change -v`
Expected: FAIL with "ImportError: cannot import name 'FixAttempt'"

**Step 3: Add FixAttempt and FixHistory models**

```python
# src/wunderunner/pipeline/models.py (append)

from datetime import UTC, datetime
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


class ConstraintStatus(str, Enum):
    """Status of a constraint."""

    HARD = "hard"  # Must be honored
    SOFT = "soft"  # Can be reconsidered with reasoning


class FixError(BaseModel):
    """Error that triggered a fix attempt."""

    type: str = Field(description="Error type: missing_dependency, build_failed")
    message: str = Field(description="Error message")
    exit_code: int | None = Field(default=None)


class FixChange(BaseModel):
    """A single change made during a fix attempt."""

    file: str = Field(description="File that was changed")
    before: str = Field(description="Content before change")
    after: str = Field(description="Content after change")


class FixAttempt(BaseModel):
    """Record of a single fix attempt."""

    attempt: int = Field(description="Attempt number: 1, 2, 3")
    timestamp: datetime = Field(default_factory=_utc_now)
    phase: str = Field(description="Phase where error occurred: BUILD, START, HEALTHCHECK")
    error: FixError
    diagnosis: str = Field(description="What we think caused the error")
    changes: list[FixChange] = Field(default_factory=list)
    outcome: str = Field(description="success, failure, partial")


class Constraint(BaseModel):
    """A constraint derived from a successful fix."""

    id: str = Field(description="Unique constraint ID: c1, c2")
    rule: str = Field(description="The constraint: MUST include pandas")
    reason: str = Field(description="Why: Required by app.py import")
    from_attempt: int = Field(description="Which attempt derived this")
    added_at: datetime = Field(default_factory=_utc_now)
    success_count: int = Field(default=0, description="Successful builds since added")
    status: ConstraintStatus = Field(default=ConstraintStatus.HARD)


class FixHistory(BaseModel):
    """Complete fix history for a project."""

    project: str = Field(description="Project name")
    created_at: datetime = Field(default_factory=_utc_now)
    attempts: list[FixAttempt] = Field(default_factory=list)
    active_constraints: list[Constraint] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_fix_attempt_records_change tests/test_pipeline_models.py::test_fix_history_manages_constraints tests/test_pipeline_models.py::test_constraint_lifecycle -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add FixAttempt and FixHistory models"
```

---

### Task 1.8: Add ErrorAnalysis and FixPlan models

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ErrorAnalysis, FixPlan, ExhaustionItem


def test_error_analysis_tracks_exhaustion():
    """ErrorAnalysis tracks what approaches have been tried."""
    analysis = ErrorAnalysis(
        error_summary="BUILD failed: missing CUDA",
        root_cause="Base image lacks CUDA libraries",
        fix_history_review="No previous CUDA attempts",
        exhaustion_status=[
            ExhaustionItem(approach="CPU-only torch", attempted=False),
            ExhaustionItem(approach="nvidia/cuda base", attempted=False),
        ],
        recommendation="continue",
        suggested_approach="Use CPU-only torch",
    )
    assert analysis.recommendation == "continue"
    assert not analysis.exhaustion_status[0].attempted


def test_fix_plan_specifies_changes():
    """FixPlan contains exact file changes."""
    plan = FixPlan(
        summary="Switch to CPU-only torch",
        dockerfile="FROM python:3.11-slim\nRUN pip install torch --index-url ...",
        changes_description="Changed torch install to CPU-only variant",
        constraints_honored=["MUST use python:3.11-slim"],
    )
    assert "torch" in plan.dockerfile
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_error_analysis_tracks_exhaustion -v`
Expected: FAIL with "ImportError: cannot import name 'ErrorAnalysis'"

**Step 3: Add ErrorAnalysis and FixPlan models**

```python
# src/wunderunner/pipeline/models.py (append)


class ExhaustionItem(BaseModel):
    """An approach that could be tried."""

    approach: str = Field(description="What could be tried: CPU-only torch")
    attempted: bool = Field(default=False, description="Whether it's been tried")


class ErrorAnalysis(BaseModel):
    """Output from ERROR-RESEARCH phase."""

    error_summary: str = Field(description="Brief error description")
    root_cause: str = Field(description="What we think caused it")
    fix_history_review: str = Field(description="Summary of previous attempts")
    exhaustion_status: list[ExhaustionItem] = Field(default_factory=list)
    recommendation: str = Field(description="continue or stop")
    suggested_approach: str | None = Field(default=None, description="What to try next")


class FixPlan(BaseModel):
    """Output from FIX-PLAN phase - surgical changes."""

    summary: str = Field(description="Brief description of the fix")
    dockerfile: str = Field(description="Updated Dockerfile content")
    compose: str | None = Field(default=None, description="Updated compose if needed")
    changes_description: str = Field(description="What changed and why")
    constraints_honored: list[str] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_error_analysis_tracks_exhaustion tests/test_pipeline_models.py::test_fix_plan_specifies_changes -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ErrorAnalysis and FixPlan models"
```

---

### Task 1.9: Add ImplementResult model

**Files:**
- Modify: `src/wunderunner/pipeline/models.py`
- Modify: `tests/test_pipeline_models.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_models.py (append)

from wunderunner.pipeline.models import ImplementResult


def test_implement_result_success():
    """ImplementResult tracks successful execution."""
    result = ImplementResult(success=True, files_written=["Dockerfile", "docker-compose.yaml"])
    assert result.success
    assert result.error is None


def test_implement_result_failure():
    """ImplementResult captures error details."""
    result = ImplementResult(
        success=False,
        files_written=["Dockerfile"],
        phase="BUILD",
        error="npm ERR! Missing script: build",
        logs="/path/to/logs/attempt-1.log",
    )
    assert not result.success
    assert result.phase == "BUILD"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_models.py::test_implement_result_success -v`
Expected: FAIL with "ImportError: cannot import name 'ImplementResult'"

**Step 3: Add ImplementResult model**

```python
# src/wunderunner/pipeline/models.py (append)


class ImplementResult(BaseModel):
    """Output from IMPLEMENT phase."""

    success: bool = Field(description="Whether all verification passed")
    files_written: list[str] = Field(default_factory=list, description="Files created/updated")
    phase: str | None = Field(default=None, description="Phase that failed: BUILD, START, HEALTHCHECK")
    error: str | None = Field(default=None, description="Error message if failed")
    logs: str | None = Field(default=None, description="Path to log file")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_models.py::test_implement_result_success tests/test_pipeline_models.py::test_implement_result_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat(pipeline): add ImplementResult model"
```

---

**Part 1 Complete.** All artifact models defined. Next: Part 2 (Research Phase Specialists).
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
## Part 3: Plan Phase

The PLAN phase reads `research.md` and generates exact file contents in `plan.md`.

---

### Task 3.1: Create plan module structure

**Files:**
- Create: `src/wunderunner/pipeline/plan/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/plan
```

```python
# src/wunderunner/pipeline/plan/__init__.py
"""PLAN phase - generate exact containerization content."""

from wunderunner.pipeline.plan.agent import generate_plan

__all__ = ["generate_plan"]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/plan/
git commit -m "feat(pipeline): add plan phase module structure"
```

---

### Task 3.2: Add plan generation agent

**Files:**
- Create: `src/wunderunner/pipeline/plan/agent.py`
- Test: `tests/test_pipeline_plan_agent.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_plan_agent.py
"""Tests for PLAN phase agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep
from wunderunner.pipeline.plan.agent import generate_plan


@pytest.fixture
def research_content() -> str:
    """Sample research.md content."""
    return """# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11
- **Framework:** fastapi
- **Entrypoint:** src/main.py

## Dependencies
- **Package Manager:** uv
- **Start Command:** `uvicorn src.main:app --host 0.0.0.0`

## Configuration

### Environment Variables
| Name | Required | Secret | Service | Default |
|------|----------|--------|---------|---------|
| DATABASE_URL | Yes | Yes | postgres | - |

## Backing Services
- **postgres** (v15) → `DATABASE_URL`
"""


@pytest.mark.asyncio
async def test_generate_plan_returns_containerization_plan(tmp_path: Path, research_content: str):
    """generate_plan returns ContainerizationPlan with exact content."""
    mock_plan = ContainerizationPlan(
        summary="Python 3.11 FastAPI app with PostgreSQL",
        dockerfile="""FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY src/ ./src/
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0"]
""",
        compose="""services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      - DATABASE_URL
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
""",
        verification=[
            VerificationStep(command="docker compose build", expected="exit 0", phase="BUILD"),
            VerificationStep(command="docker compose up -d", expected="containers start", phase="START"),
        ],
        reasoning="Using uv for fast dependency resolution, slim image for size",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=[])

    assert isinstance(result, ContainerizationPlan)
    assert "FROM python:3.11" in result.dockerfile
    assert "postgres:15" in result.compose
    assert len(result.verification) == 2


@pytest.mark.asyncio
async def test_generate_plan_honors_constraints(tmp_path: Path, research_content: str):
    """generate_plan includes constraints in output."""
    constraints = ["MUST use python:3.11-slim base image", "MUST include pandas"]

    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Honoring constraints",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=constraints)

    assert result.constraints_honored == constraints
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_plan_agent.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan generation agent**

```python
# src/wunderunner/pipeline/plan/agent.py
"""PLAN phase agent.

Generates exact Dockerfile and docker-compose.yaml content from research findings.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.settings import get_model, Generation

SYSTEM_PROMPT = """\
You are generating containerization files for a software project.

Your output must contain EXACT, COMPLETE file contents - not instructions or placeholders.
The IMPLEMENT phase will write your output directly to disk without modification.

<input>
You receive:
1. research.md - Project analysis from RESEARCH phase
2. constraints - Rules from previous fixes that MUST be honored

Read the research carefully. Generate files that match the project's actual configuration.
</input>

<output_requirements>
dockerfile: Complete, valid Dockerfile content
- Start with appropriate base image for the runtime
- Install dependencies using the detected package manager
- Handle secrets with ARG/ENV pattern
- Set correct WORKDIR, COPY, EXPOSE, CMD

compose (optional): Complete docker-compose.yaml if services detected
- Include app service with build context
- Add backing services (postgres, redis, etc.) with correct images
- Wire up environment variables
- Set depends_on relationships

verification: List of commands to verify the build works
- BUILD phase: docker compose build or docker build
- START phase: docker compose up -d or docker run
- HEALTHCHECK phase: curl or wget to health endpoint if applicable

reasoning: Brief explanation of your choices
- Why this base image?
- Why this dependency installation approach?
- Any trade-offs made?

constraints_honored: Echo back any constraints you were given
- Include exact constraint text
- Only list constraints you actually honored
</output_requirements>

<dockerfile_patterns>
Python with uv:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src/ ./src/
# Secrets via ARG/ENV
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0"]
```

Python with pip:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"]
```

Node.js with npm:
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

Node.js with pnpm:
```dockerfile
FROM node:20-slim
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY . .
EXPOSE 3000
CMD ["pnpm", "start"]
```
</dockerfile_patterns>

<compose_patterns>
With PostgreSQL:
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/app
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

With Redis:
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - REDIS_URL=redis://redis:6379
  redis:
    image: redis:7-alpine
```
</compose_patterns>

<constraints_handling>
CRITICAL: If constraints are provided, you MUST honor them.

Example constraints:
- "MUST use python:3.11-slim base image" → Use exactly python:3.11-slim
- "MUST include pandas in pip install" → Add pandas to RUN pip install
- "MUST NOT use multi-stage build" → Use single stage

If a constraint conflicts with best practices, honor the constraint anyway.
The constraint exists because a previous fix attempt proved it necessary.
</constraints_handling>
"""


def _build_user_prompt(research_content: str, constraints: list[str]) -> str:
    """Build user prompt from research and constraints."""
    parts = [
        "Generate containerization files based on this research:\n",
        "## Research\n",
        research_content,
        "\n",
    ]

    if constraints:
        parts.append("## Constraints (MUST honor these)\n")
        for c in constraints:
            parts.append(f"- {c}\n")
    else:
        parts.append("## Constraints\nNone - this is the first attempt.\n")

    return "".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=ContainerizationPlan,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def generate_plan(
    project_dir: Path,
    research_content: str,
    constraints: list[str],
) -> ContainerizationPlan:
    """Generate containerization plan from research.

    Args:
        project_dir: Project root directory (for context, not used by agent).
        research_content: Content of research.md.
        constraints: Active constraints from fixes.json.

    Returns:
        ContainerizationPlan with exact file contents.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(research_content, constraints)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_plan_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/plan/agent.py tests/test_pipeline_plan_agent.py
git commit -m "feat(pipeline): add PLAN phase agent"
```

---

### Task 3.3: Add plan phase runner

**Files:**
- Modify: `src/wunderunner/pipeline/plan/__init__.py`
- Create: `src/wunderunner/pipeline/plan/runner.py`
- Test: `tests/test_pipeline_plan_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_plan_runner.py
"""Tests for PLAN phase runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.pipeline.plan.runner import run_plan


@pytest.fixture
def project_with_research(tmp_path: Path) -> Path:
    """Create project with research.md artifact."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("""# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11

## Dependencies
- **Package Manager:** uv

## Configuration
No environment variables detected.

## Backing Services
No backing services detected.
""")
    return tmp_path


@pytest.mark.asyncio
async def test_run_plan_reads_research_and_generates(project_with_research: Path):
    """run_plan reads research.md and generates plan."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Simple Python app",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        result = await run_plan(project_with_research)

    assert isinstance(result, ContainerizationPlan)


@pytest.mark.asyncio
async def test_run_plan_writes_artifact(project_with_research: Path):
    """run_plan writes plan.md artifact."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        verification=[],
        reasoning="Simple",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        await run_plan(project_with_research)

    plan_path = project_with_research / ".wunderunner" / "plan.md"
    assert plan_path.exists()
    content = plan_path.read_text()
    assert "FROM python:3.11-slim" in content


@pytest.mark.asyncio
async def test_run_plan_raises_if_no_research(tmp_path: Path):
    """run_plan raises if research.md missing."""
    with pytest.raises(FileNotFoundError):
        await run_plan(tmp_path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_plan_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan phase runner**

```python
# src/wunderunner/pipeline/plan/runner.py
"""PLAN phase runner.

Reads research.md, loads constraints, generates plan, writes plan.md.
"""

from pathlib import Path

from wunderunner.pipeline.artifacts import (
    read_research,
    write_plan,
    read_fix_history,
)
from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.pipeline.plan.agent import generate_plan


async def run_plan(project_dir: Path) -> ContainerizationPlan:
    """Execute PLAN phase.

    Reads research.md artifact, loads any active constraints from fixes.json,
    generates containerization plan, and writes plan.md.

    Args:
        project_dir: Project root directory.

    Returns:
        Generated ContainerizationPlan.

    Raises:
        FileNotFoundError: If research.md doesn't exist.
    """
    # Read research artifact
    research_content = await read_research(project_dir)

    # Load constraints from fix history
    constraints: list[str] = []
    fix_history = await read_fix_history(project_dir)
    if fix_history:
        constraints = [
            c.rule for c in fix_history.active_constraints
            if c.status.value == "hard"
        ]

    # Generate plan
    plan = await generate_plan(project_dir, research_content, constraints)

    # Write artifact
    await write_plan(project_dir, plan)

    return plan
```

**Step 4: Update __init__.py**

```python
# src/wunderunner/pipeline/plan/__init__.py
"""PLAN phase - generate exact containerization content."""

from wunderunner.pipeline.plan.runner import run_plan

__all__ = ["run_plan"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_plan_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/plan/ tests/test_pipeline_plan_runner.py
git commit -m "feat(pipeline): add PLAN phase runner"
```

---

**Part 3 Complete.** PLAN phase with agent and runner. Next: Part 4 (Implement Phase).
## Part 4: Implement Phase

The IMPLEMENT phase reads `plan.md`, writes files, and runs verification. Mostly code, minimal LLM.

---

### Task 4.1: Create implement module structure

**Files:**
- Create: `src/wunderunner/pipeline/implement/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/implement
```

```python
# src/wunderunner/pipeline/implement/__init__.py
"""IMPLEMENT phase - write files and run verification."""

from wunderunner.pipeline.implement.runner import run_implement

__all__ = ["run_implement"]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/implement/
git commit -m "feat(pipeline): add implement phase module structure"
```

---

### Task 4.2: Add plan parser

**Files:**
- Create: `src/wunderunner/pipeline/implement/parser.py`
- Test: `tests/test_pipeline_implement_parser.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_parser.py
"""Tests for plan.md parser."""

import pytest
from wunderunner.pipeline.implement.parser import parse_plan, ParsedPlan


def test_parse_plan_extracts_dockerfile():
    """parse_plan extracts Dockerfile content from code block."""
    plan_md = """# Containerization Plan

## Summary
Python app

## Files

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
```

## Reasoning
Simple setup
"""
    result = parse_plan(plan_md)

    assert isinstance(result, ParsedPlan)
    assert result.dockerfile is not None
    assert "FROM python:3.11-slim" in result.dockerfile
    assert result.compose is None


def test_parse_plan_extracts_compose():
    """parse_plan extracts docker-compose.yaml content."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
```

### docker-compose.yaml
```yaml
services:
  app:
    build: .
    ports:
      - "3000:3000"
```

## Verification
1. `docker compose build` → exit 0
"""
    result = parse_plan(plan_md)

    assert result.dockerfile is not None
    assert result.compose is not None
    assert "services:" in result.compose
    assert "build: ." in result.compose


def test_parse_plan_extracts_verification():
    """parse_plan extracts verification steps."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM python:3.11
```

## Verification
1. `docker build -t app .` → exit 0
2. `docker run -d -p 8000:8000 app` → container starts
3. `curl localhost:8000/health` → 200 OK
"""
    result = parse_plan(plan_md)

    assert len(result.verification_steps) == 3
    assert result.verification_steps[0].command == "docker build -t app ."
    assert result.verification_steps[0].expected == "exit 0"


def test_parse_plan_handles_missing_sections():
    """parse_plan handles minimal plan."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM alpine
```
"""
    result = parse_plan(plan_md)

    assert result.dockerfile == "FROM alpine"
    assert result.compose is None
    assert result.verification_steps == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_parser.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan parser**

```python
# src/wunderunner/pipeline/implement/parser.py
"""Parse plan.md artifact to extract file contents and verification steps."""

import re
from dataclasses import dataclass


@dataclass
class VerificationStep:
    """A verification step extracted from plan."""

    command: str
    expected: str


@dataclass
class ParsedPlan:
    """Parsed contents of plan.md."""

    dockerfile: str | None
    compose: str | None
    verification_steps: list[VerificationStep]


def parse_plan(plan_content: str) -> ParsedPlan:
    """Parse plan.md content to extract file contents.

    Extracts:
    - Dockerfile content from ```dockerfile code block
    - docker-compose.yaml content from ```yaml code block
    - Verification steps from numbered list

    Args:
        plan_content: Raw markdown content of plan.md.

    Returns:
        ParsedPlan with extracted contents.
    """
    dockerfile = _extract_code_block(plan_content, "dockerfile")
    compose = _extract_code_block(plan_content, "yaml")
    verification = _extract_verification_steps(plan_content)

    return ParsedPlan(
        dockerfile=dockerfile,
        compose=compose,
        verification_steps=verification,
    )


def _extract_code_block(content: str, language: str) -> str | None:
    """Extract content from a fenced code block.

    Args:
        content: Markdown content.
        language: Code block language (dockerfile, yaml).

    Returns:
        Code block content without fences, or None if not found.
    """
    # Match ```language ... ``` blocks
    pattern = rf"```{language}\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def _extract_verification_steps(content: str) -> list[VerificationStep]:
    """Extract verification steps from numbered list.

    Expected format:
    1. `command` → expected
    2. `command` → expected

    Args:
        content: Markdown content.

    Returns:
        List of VerificationStep objects.
    """
    steps = []

    # Find the Verification section
    verification_match = re.search(r"## Verification\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not verification_match:
        return steps

    verification_section = verification_match.group(1)

    # Match numbered items: 1. `command` → expected
    pattern = r"\d+\.\s+`([^`]+)`\s+→\s+(.+)"
    for match in re.finditer(pattern, verification_section):
        command = match.group(1).strip()
        expected = match.group(2).strip()
        steps.append(VerificationStep(command=command, expected=expected))

    return steps
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/parser.py tests/test_pipeline_implement_parser.py
git commit -m "feat(pipeline): add plan.md parser"
```

---

### Task 4.3: Add file writer

**Files:**
- Create: `src/wunderunner/pipeline/implement/writer.py`
- Test: `tests/test_pipeline_implement_writer.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_writer.py
"""Tests for file writer."""

import pytest
from pathlib import Path

from wunderunner.pipeline.implement.writer import write_files
from wunderunner.pipeline.implement.parser import ParsedPlan, VerificationStep


@pytest.mark.asyncio
async def test_write_files_creates_dockerfile(tmp_path: Path):
    """write_files creates Dockerfile in project directory."""
    plan = ParsedPlan(
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    dockerfile_path = tmp_path / "Dockerfile"
    assert dockerfile_path.exists()
    assert "FROM python:3.11-slim" in dockerfile_path.read_text()


@pytest.mark.asyncio
async def test_write_files_creates_compose(tmp_path: Path):
    """write_files creates docker-compose.yaml."""
    plan = ParsedPlan(
        dockerfile="FROM node:20\n",
        compose="services:\n  app:\n    build: .\n",
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" in files
    compose_path = tmp_path / "docker-compose.yaml"
    assert compose_path.exists()
    assert "services:" in compose_path.read_text()


@pytest.mark.asyncio
async def test_write_files_skips_none_values(tmp_path: Path):
    """write_files skips files with None content."""
    plan = ParsedPlan(
        dockerfile="FROM alpine\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" not in files
    assert not (tmp_path / "docker-compose.yaml").exists()


@pytest.mark.asyncio
async def test_write_files_overwrites_existing(tmp_path: Path):
    """write_files overwrites existing files."""
    # Create existing Dockerfile
    (tmp_path / "Dockerfile").write_text("FROM old:version\n")

    plan = ParsedPlan(
        dockerfile="FROM new:version\n",
        compose=None,
        verification_steps=[],
    )

    await write_files(tmp_path, plan)

    assert "FROM new:version" in (tmp_path / "Dockerfile").read_text()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_writer.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write file writer**

```python
# src/wunderunner/pipeline/implement/writer.py
"""Write files from parsed plan to project directory."""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.implement.parser import ParsedPlan


async def write_files(project_dir: Path, plan: ParsedPlan) -> list[str]:
    """Write Dockerfile and docker-compose.yaml to project directory.

    Args:
        project_dir: Project root directory.
        plan: ParsedPlan with file contents.

    Returns:
        List of filenames that were written.
    """
    written: list[str] = []

    if plan.dockerfile:
        dockerfile_path = project_dir / "Dockerfile"
        async with aiofiles.open(dockerfile_path, "w") as f:
            await f.write(plan.dockerfile)
        written.append("Dockerfile")

    if plan.compose:
        compose_path = project_dir / "docker-compose.yaml"
        async with aiofiles.open(compose_path, "w") as f:
            await f.write(plan.compose)
        written.append("docker-compose.yaml")

    return written
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/writer.py tests/test_pipeline_implement_writer.py
git commit -m "feat(pipeline): add file writer"
```

---

### Task 4.4: Add verification runner

**Files:**
- Create: `src/wunderunner/pipeline/implement/verify.py`
- Test: `tests/test_pipeline_implement_verify.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_verify.py
"""Tests for verification runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.implement.verify import (
    run_verification,
    VerificationResult,
)
from wunderunner.pipeline.implement.parser import VerificationStep


@pytest.mark.asyncio
async def test_run_verification_success(tmp_path: Path):
    """run_verification returns success when all steps pass."""
    steps = [
        VerificationStep(command="echo hello", expected="exit 0"),
    ]

    # Mock subprocess to return success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "hello\n"
    mock_process.stderr = ""

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process
        mock_process.communicate = AsyncMock(return_value=(b"hello\n", b""))

        result = await run_verification(tmp_path, steps)

    assert isinstance(result, VerificationResult)
    assert result.success is True
    assert result.failed_step is None


@pytest.mark.asyncio
async def test_run_verification_failure(tmp_path: Path):
    """run_verification returns failure with details on error."""
    steps = [
        VerificationStep(command="docker build .", expected="exit 0"),
    ]

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Error: Dockerfile not found"))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_verification(tmp_path, steps)

    assert result.success is False
    assert result.failed_step == "docker build ."
    assert "Dockerfile not found" in result.error


@pytest.mark.asyncio
async def test_run_verification_stops_on_first_failure(tmp_path: Path):
    """run_verification stops after first failed step."""
    steps = [
        VerificationStep(command="step1", expected="exit 0"),
        VerificationStep(command="step2", expected="exit 0"),
    ]

    call_count = 0

    async def mock_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        process = MagicMock()
        process.returncode = 1  # Always fail
        process.communicate = AsyncMock(return_value=(b"", b"error"))
        return process

    with patch("asyncio.create_subprocess_shell", side_effect=mock_subprocess):
        result = await run_verification(tmp_path, steps)

    assert result.success is False
    assert call_count == 1  # Only first step ran
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_verify.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write verification runner**

```python
# src/wunderunner/pipeline/implement/verify.py
"""Run verification commands and capture results."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from wunderunner.pipeline.implement.parser import VerificationStep


@dataclass
class VerificationResult:
    """Result of running verification steps."""

    success: bool
    failed_step: str | None = None
    phase: str | None = None
    error: str | None = None
    stdout: str | None = None
    stderr: str | None = None


async def run_verification(
    project_dir: Path,
    steps: list[VerificationStep],
) -> VerificationResult:
    """Execute verification steps sequentially.

    Stops on first failure and returns error details.

    Args:
        project_dir: Directory to run commands in.
        steps: List of verification steps from plan.

    Returns:
        VerificationResult with success status and error details if failed.
    """
    for step in steps:
        result = await _run_step(project_dir, step)
        if not result.success:
            return result

    return VerificationResult(success=True)


async def _run_step(project_dir: Path, step: VerificationStep) -> VerificationResult:
    """Run a single verification step.

    Args:
        project_dir: Directory to run command in.
        step: Verification step with command and expected outcome.

    Returns:
        VerificationResult for this step.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            step.command,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # Check if step passed based on expected outcome
        passed = _check_expected(step.expected, process.returncode, stdout_str, stderr_str)

        if passed:
            return VerificationResult(
                success=True,
                stdout=stdout_str,
                stderr=stderr_str,
            )
        else:
            return VerificationResult(
                success=False,
                failed_step=step.command,
                phase=_infer_phase(step.command),
                error=stderr_str or stdout_str or f"Command exited with code {process.returncode}",
                stdout=stdout_str,
                stderr=stderr_str,
            )

    except Exception as e:
        return VerificationResult(
            success=False,
            failed_step=step.command,
            error=str(e),
        )


def _check_expected(expected: str, returncode: int, stdout: str, stderr: str) -> bool:
    """Check if command output matches expected outcome.

    Args:
        expected: Expected outcome string (e.g., "exit 0", "200 OK").
        returncode: Process return code.
        stdout: Standard output.
        stderr: Standard error.

    Returns:
        True if outcome matches expected.
    """
    expected_lower = expected.lower()

    # Check for exit code expectations
    if "exit 0" in expected_lower:
        return returncode == 0
    if "exit" in expected_lower:
        # Generic exit check - non-zero is failure
        return returncode == 0

    # Check for content in output
    if "200" in expected or "ok" in expected_lower:
        return "200" in stdout or "ok" in stdout.lower()

    # Check for container/service expectations
    if "start" in expected_lower or "running" in expected_lower:
        return returncode == 0

    # Default: success if exit code is 0
    return returncode == 0


def _infer_phase(command: str) -> str:
    """Infer the phase from the command.

    Args:
        command: The verification command.

    Returns:
        Phase name: BUILD, START, or HEALTHCHECK.
    """
    command_lower = command.lower()

    if "build" in command_lower:
        return "BUILD"
    if "up" in command_lower or "run" in command_lower:
        return "START"
    if "curl" in command_lower or "wget" in command_lower or "health" in command_lower:
        return "HEALTHCHECK"

    return "BUILD"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_verify.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/verify.py tests/test_pipeline_implement_verify.py
git commit -m "feat(pipeline): add verification runner"
```

---

### Task 4.5: Add log capture

**Files:**
- Create: `src/wunderunner/pipeline/implement/logs.py`
- Test: `tests/test_pipeline_implement_logs.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_logs.py
"""Tests for log capture."""

import pytest
from pathlib import Path

from wunderunner.pipeline.implement.logs import save_logs, get_log_path


@pytest.mark.asyncio
async def test_save_logs_creates_file(tmp_path: Path):
    """save_logs creates log file in .wunderunner/logs/."""
    path = await save_logs(
        project_dir=tmp_path,
        attempt=1,
        stdout="Build output",
        stderr="Error message",
    )

    assert path.exists()
    assert ".wunderunner/logs/attempt-1.log" in str(path)

    content = path.read_text()
    assert "Build output" in content
    assert "Error message" in content


def test_get_log_path(tmp_path: Path):
    """get_log_path returns correct path."""
    path = get_log_path(tmp_path, 3)
    assert path == tmp_path / ".wunderunner" / "logs" / "attempt-3.log"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_logs.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write log capture**

```python
# src/wunderunner/pipeline/implement/logs.py
"""Capture and save verification logs."""

from pathlib import Path

import aiofiles

from wunderunner.settings import get_settings


def get_log_path(project_dir: Path, attempt: int) -> Path:
    """Get path to log file for an attempt.

    Args:
        project_dir: Project root directory.
        attempt: Attempt number.

    Returns:
        Path to log file.
    """
    settings = get_settings()
    return project_dir / settings.cache_dir / "logs" / f"attempt-{attempt}.log"


async def save_logs(
    project_dir: Path,
    attempt: int,
    stdout: str | None,
    stderr: str | None,
    command: str | None = None,
) -> Path:
    """Save verification output to log file.

    Args:
        project_dir: Project root directory.
        attempt: Attempt number.
        stdout: Standard output content.
        stderr: Standard error content.
        command: Command that was run (optional).

    Returns:
        Path to created log file.
    """
    log_path = get_log_path(project_dir, attempt)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    content_parts = []

    if command:
        content_parts.append(f"Command: {command}\n")
        content_parts.append("=" * 50 + "\n\n")

    if stdout:
        content_parts.append("=== STDOUT ===\n")
        content_parts.append(stdout)
        content_parts.append("\n\n")

    if stderr:
        content_parts.append("=== STDERR ===\n")
        content_parts.append(stderr)
        content_parts.append("\n")

    async with aiofiles.open(log_path, "w") as f:
        await f.write("".join(content_parts))

    return log_path
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_logs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/implement/logs.py tests/test_pipeline_implement_logs.py
git commit -m "feat(pipeline): add log capture"
```

---

### Task 4.6: Add implement phase runner

**Files:**
- Create: `src/wunderunner/pipeline/implement/runner.py`
- Test: `tests/test_pipeline_implement_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_implement_runner.py
"""Tests for IMPLEMENT phase runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.models import ImplementResult
from wunderunner.pipeline.implement.runner import run_implement


@pytest.fixture
def project_with_plan(tmp_path: Path) -> Path:
    """Create project with plan.md artifact."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "plan.md").write_text("""# Containerization Plan

## Summary
Python app

## Files

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
```

## Verification
1. `docker build -t app .` → exit 0
""")
    return tmp_path


@pytest.mark.asyncio
async def test_run_implement_writes_files(project_with_plan: Path):
    """run_implement writes Dockerfile from plan."""
    # Mock verification to succeed
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_implement(project_with_plan, attempt=1)

    assert (project_with_plan / "Dockerfile").exists()
    assert "FROM python:3.11-slim" in (project_with_plan / "Dockerfile").read_text()


@pytest.mark.asyncio
async def test_run_implement_returns_success(project_with_plan: Path):
    """run_implement returns success when verification passes."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"Built!", b""))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_implement(project_with_plan, attempt=1)

    assert isinstance(result, ImplementResult)
    assert result.success is True
    assert "Dockerfile" in result.files_written


@pytest.mark.asyncio
async def test_run_implement_returns_failure_with_logs(project_with_plan: Path):
    """run_implement returns failure with log path on error."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"Build failed"))

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_process

        result = await run_implement(project_with_plan, attempt=2)

    assert result.success is False
    assert result.phase == "BUILD"
    assert "Build failed" in result.error
    assert result.logs is not None
    assert "attempt-2.log" in result.logs
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_implement_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implement phase runner**

```python
# src/wunderunner/pipeline/implement/runner.py
"""IMPLEMENT phase runner.

Reads plan.md, writes files, runs verification.
"""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.artifacts import get_artifact_path
from wunderunner.pipeline.models import ImplementResult
from wunderunner.pipeline.implement.parser import parse_plan
from wunderunner.pipeline.implement.writer import write_files
from wunderunner.pipeline.implement.verify import run_verification
from wunderunner.pipeline.implement.logs import save_logs


async def run_implement(project_dir: Path, attempt: int = 1) -> ImplementResult:
    """Execute IMPLEMENT phase.

    Reads plan.md, writes files to project directory, runs verification steps.

    Args:
        project_dir: Project root directory.
        attempt: Current attempt number (for log naming).

    Returns:
        ImplementResult with success status and error details if failed.

    Raises:
        FileNotFoundError: If plan.md doesn't exist.
    """
    # Read plan artifact
    plan_path = get_artifact_path(project_dir, "plan.md")
    async with aiofiles.open(plan_path) as f:
        plan_content = await f.read()

    # Parse plan
    parsed = parse_plan(plan_content)

    if not parsed.dockerfile:
        return ImplementResult(
            success=False,
            error="No Dockerfile found in plan.md",
        )

    # Write files
    files_written = await write_files(project_dir, parsed)

    # Run verification
    verify_result = await run_verification(project_dir, parsed.verification_steps)

    if verify_result.success:
        return ImplementResult(
            success=True,
            files_written=files_written,
        )

    # Save logs on failure
    log_path = await save_logs(
        project_dir=project_dir,
        attempt=attempt,
        stdout=verify_result.stdout,
        stderr=verify_result.stderr,
        command=verify_result.failed_step,
    )

    return ImplementResult(
        success=False,
        files_written=files_written,
        phase=verify_result.phase,
        error=verify_result.error,
        logs=str(log_path),
    )
```

**Step 4: Update __init__.py**

```python
# src/wunderunner/pipeline/implement/__init__.py
"""IMPLEMENT phase - write files and run verification."""

from wunderunner.pipeline.implement.runner import run_implement

__all__ = ["run_implement"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_implement_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/implement/ tests/test_pipeline_implement_runner.py
git commit -m "feat(pipeline): add IMPLEMENT phase runner"
```

---

**Part 4 Complete.** IMPLEMENT phase with parser, writer, verification, and log capture. Next: Part 5 (Error Handling).
## Part 5: Error Handling Flow

When IMPLEMENT fails, we run ERROR-RESEARCH → FIX-PLAN → IMPLEMENT cycle with constraint tracking.

---

### Task 5.1: Create errors module structure

**Files:**
- Create: `src/wunderunner/pipeline/errors/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/errors
```

```python
# src/wunderunner/pipeline/errors/__init__.py
"""Error handling - ERROR-RESEARCH and FIX-PLAN phases."""

from wunderunner.pipeline.errors.research import run_error_research
from wunderunner.pipeline.errors.fix_plan import run_fix_plan
from wunderunner.pipeline.errors.constraints import (
    update_constraints,
    increment_success_counts,
)

__all__ = [
    "run_error_research",
    "run_fix_plan",
    "update_constraints",
    "increment_success_counts",
]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/errors/
git commit -m "feat(pipeline): add errors module structure"
```

---

### Task 5.2: Add constraint management

**Files:**
- Create: `src/wunderunner/pipeline/errors/constraints.py`
- Test: `tests/test_pipeline_constraints.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_constraints.py
"""Tests for constraint management."""

import pytest
from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    FixError,
    Constraint,
    ConstraintStatus,
)
from wunderunner.pipeline.errors.constraints import (
    update_constraints,
    increment_success_counts,
    derive_constraint,
)


def test_derive_constraint_creates_hard_constraint():
    """derive_constraint creates a hard constraint from fix attempt."""
    attempt = FixAttempt(
        attempt=1,
        phase="BUILD",
        error=FixError(type="missing_dependency", message="No module pandas"),
        diagnosis="pandas not installed",
        outcome="success",
    )

    constraint = derive_constraint(attempt, "MUST include pandas in pip install")

    assert constraint.status == ConstraintStatus.HARD
    assert constraint.rule == "MUST include pandas in pip install"
    assert constraint.from_attempt == 1
    assert constraint.success_count == 0


def test_increment_success_counts_increments():
    """increment_success_counts adds 1 to all constraint success_count."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=0),
            Constraint(id="c2", rule="rule2", reason="r2", from_attempt=2, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 1
    assert updated.active_constraints[1].success_count == 3


def test_increment_success_counts_makes_soft_at_threshold():
    """Constraints become soft after 3 successful builds."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 3
    assert updated.active_constraints[0].status == ConstraintStatus.SOFT


def test_update_constraints_adds_new():
    """update_constraints adds new constraint to history."""
    history = FixHistory(project="test", active_constraints=[])
    new_constraint = Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1)

    updated = update_constraints(history, new_constraint)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].rule == "rule1"


def test_update_constraints_resets_violated():
    """update_constraints resets violated constraint to hard."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(
                id="c1", rule="rule1", reason="r1", from_attempt=1,
                success_count=5, status=ConstraintStatus.SOFT,
            ),
        ],
    )

    # Same rule, new attempt = was violated
    new_constraint = Constraint(id="c1-v2", rule="rule1", reason="violated", from_attempt=3)

    updated = update_constraints(history, new_constraint, violated=True)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].status == ConstraintStatus.HARD
    assert updated.active_constraints[0].success_count == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_constraints.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write constraint management**

```python
# src/wunderunner/pipeline/errors/constraints.py
"""Constraint management for fix history."""

from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    Constraint,
    ConstraintStatus,
)

SOFT_THRESHOLD = 3  # Constraints become soft after this many successes


def derive_constraint(attempt: FixAttempt, rule: str) -> Constraint:
    """Create a constraint from a successful fix attempt.

    Args:
        attempt: The fix attempt that succeeded.
        rule: The constraint rule text.

    Returns:
        New hard constraint.
    """
    return Constraint(
        id=f"c{attempt.attempt}",
        rule=rule,
        reason=attempt.diagnosis,
        from_attempt=attempt.attempt,
        success_count=0,
        status=ConstraintStatus.HARD,
    )


def increment_success_counts(history: FixHistory) -> FixHistory:
    """Increment success_count for all constraints after successful build.

    Constraints become soft after reaching SOFT_THRESHOLD successes.

    Args:
        history: Current fix history.

    Returns:
        Updated fix history with incremented counts.
    """
    updated_constraints = []

    for constraint in history.active_constraints:
        new_count = constraint.success_count + 1
        new_status = constraint.status

        if new_count >= SOFT_THRESHOLD and constraint.status == ConstraintStatus.HARD:
            new_status = ConstraintStatus.SOFT

        updated_constraints.append(
            Constraint(
                id=constraint.id,
                rule=constraint.rule,
                reason=constraint.reason,
                from_attempt=constraint.from_attempt,
                added_at=constraint.added_at,
                success_count=new_count,
                status=new_status,
            )
        )

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )


def update_constraints(
    history: FixHistory,
    new_constraint: Constraint,
    violated: bool = False,
) -> FixHistory:
    """Add or update a constraint in history.

    If violated=True, resets an existing constraint with same rule to hard.

    Args:
        history: Current fix history.
        new_constraint: Constraint to add or update.
        violated: Whether this is a violated constraint being reset.

    Returns:
        Updated fix history.
    """
    updated_constraints = []

    # Check if constraint with same rule exists
    found_existing = False
    for existing in history.active_constraints:
        if existing.rule == new_constraint.rule:
            found_existing = True
            if violated:
                # Reset to hard with 0 success count
                updated_constraints.append(
                    Constraint(
                        id=new_constraint.id,
                        rule=new_constraint.rule,
                        reason=new_constraint.reason,
                        from_attempt=new_constraint.from_attempt,
                        success_count=0,
                        status=ConstraintStatus.HARD,
                    )
                )
            else:
                # Keep existing
                updated_constraints.append(existing)
        else:
            updated_constraints.append(existing)

    # Add new if not found
    if not found_existing:
        updated_constraints.append(new_constraint)

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_constraints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/constraints.py tests/test_pipeline_constraints.py
git commit -m "feat(pipeline): add constraint management"
```

---

### Task 5.3: Add ERROR-RESEARCH agent

**Files:**
- Create: `src/wunderunner/pipeline/errors/research.py`
- Test: `tests/test_pipeline_error_research.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_error_research.py
"""Tests for ERROR-RESEARCH agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import (
    ErrorAnalysis,
    ExhaustionItem,
    FixHistory,
    FixAttempt,
    FixError,
)
from wunderunner.pipeline.errors.research import run_error_research


@pytest.fixture
def error_context() -> dict:
    """Sample error context."""
    return {
        "phase": "BUILD",
        "error": "npm ERR! Missing script: build",
        "log_path": "/tmp/logs/attempt-1.log",
    }


@pytest.fixture
def fix_history() -> FixHistory:
    """Sample fix history with one attempt."""
    return FixHistory(
        project="test",
        attempts=[
            FixAttempt(
                attempt=1,
                phase="BUILD",
                error=FixError(type="syntax", message="Dockerfile syntax error"),
                diagnosis="Missing FROM instruction",
                outcome="success",
            )
        ],
        active_constraints=[],
    )


@pytest.mark.asyncio
async def test_run_error_research_returns_analysis(
    tmp_path: Path, error_context: dict, fix_history: FixHistory
):
    """run_error_research returns ErrorAnalysis."""
    mock_analysis = ErrorAnalysis(
        error_summary="BUILD failed: missing build script",
        root_cause="package.json has no build script",
        fix_history_review="1 previous attempt for syntax error",
        exhaustion_status=[
            ExhaustionItem(approach="Add build script", attempted=False),
            ExhaustionItem(approach="Use different start command", attempted=False),
        ],
        recommendation="continue",
        suggested_approach="Add build script to package.json",
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="# Project Research\n...",
            fix_history=fix_history,
        )

    assert isinstance(result, ErrorAnalysis)
    assert result.recommendation == "continue"
    assert len(result.exhaustion_status) == 2


@pytest.mark.asyncio
async def test_run_error_research_detects_exhaustion(
    tmp_path: Path, error_context: dict
):
    """run_error_research can recommend stopping."""
    history = FixHistory(
        project="test",
        attempts=[
            FixAttempt(attempt=1, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
            FixAttempt(attempt=2, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
            FixAttempt(attempt=3, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
        ],
        active_constraints=[],
    )

    mock_analysis = ErrorAnalysis(
        error_summary="Persistent failure",
        root_cause="Unknown",
        fix_history_review="3 failed attempts",
        exhaustion_status=[
            ExhaustionItem(approach="Approach 1", attempted=True),
            ExhaustionItem(approach="Approach 2", attempted=True),
        ],
        recommendation="stop",
        suggested_approach=None,
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="...",
            fix_history=history,
        )

    assert result.recommendation == "stop"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_error_research.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write ERROR-RESEARCH agent**

```python
# src/wunderunner/pipeline/errors/research.py
"""ERROR-RESEARCH agent.

Analyzes build/runtime errors and determines fix approach.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ErrorAnalysis, FixHistory
from wunderunner.settings import get_model, Generation

SYSTEM_PROMPT = """\
You are analyzing a containerization error to determine the fix approach.

<input>
You receive:
1. Error context (phase, error message, log path)
2. Original research.md (project context)
3. Fix history (previous attempts and their outcomes)
</input>

<task>
1. Understand what went wrong
2. Review what fixes have already been tried
3. Determine if there are untried approaches
4. Recommend whether to continue or stop
</task>

<error_analysis>
Common error patterns and fixes:

BUILD phase:
- "Missing script: X" → Add script to package.json or change CMD
- "Module not found" → Add dependency or fix import path
- "COPY failed: file not found" → Fix path in Dockerfile
- "npm ERR!" → Check package.json, lockfile, or node version
- "pip: No matching distribution" → Check Python version or package name

START phase:
- "Port already in use" → Change port mapping
- "Connection refused" → Service not ready, add healthcheck/wait
- "Permission denied" → Add chmod or run as different user
- "ENOENT" → Missing file, check COPY commands

HEALTHCHECK phase:
- "Connection refused" → App not listening, check port/host
- "404" → Endpoint doesn't exist, check route
- "500" → App error, check logs
</error_analysis>

<exhaustion_check>
Track what approaches have been tried:
- List 3-5 standard approaches for this error type
- Mark each as attempted or not based on fix history
- If all standard approaches are exhausted, recommend "stop"
</exhaustion_check>

<output>
error_summary: Brief description of what failed
root_cause: Your diagnosis of why it failed
fix_history_review: Summary of previous attempts
exhaustion_status: List of approaches with attempted status
recommendation: "continue" or "stop"
suggested_approach: What to try next (null if stopping)
</output>
"""


def _build_user_prompt(
    error_context: dict,
    research_content: str,
    fix_history: FixHistory,
) -> str:
    """Build user prompt from error context and history."""
    parts = []

    # Error context
    parts.append("## Error Context\n")
    parts.append(f"- Phase: {error_context.get('phase', 'UNKNOWN')}")
    parts.append(f"- Error: {error_context.get('error', 'Unknown error')}")
    if error_context.get("log_path"):
        parts.append(f"- Log: {error_context['log_path']}")
    parts.append("")

    # Research context
    parts.append("## Project Research\n")
    parts.append(research_content)
    parts.append("")

    # Fix history
    parts.append("## Fix History\n")
    if fix_history.attempts:
        for attempt in fix_history.attempts:
            parts.append(f"### Attempt {attempt.attempt}")
            parts.append(f"- Phase: {attempt.phase}")
            parts.append(f"- Error: {attempt.error.message}")
            parts.append(f"- Diagnosis: {attempt.diagnosis}")
            parts.append(f"- Outcome: {attempt.outcome}")
            parts.append("")
    else:
        parts.append("No previous attempts.\n")

    return "\n".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=ErrorAnalysis,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def run_error_research(
    project_dir: Path,
    error_context: dict,
    research_content: str,
    fix_history: FixHistory,
) -> ErrorAnalysis:
    """Run ERROR-RESEARCH phase.

    Args:
        project_dir: Project root directory.
        error_context: Dict with phase, error, log_path.
        research_content: Content of research.md.
        fix_history: Previous fix attempts.

    Returns:
        ErrorAnalysis with diagnosis and recommendation.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(error_context, research_content, fix_history)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_error_research.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/research.py tests/test_pipeline_error_research.py
git commit -m "feat(pipeline): add ERROR-RESEARCH agent"
```

---

### Task 5.4: Add FIX-PLAN agent

**Files:**
- Create: `src/wunderunner/pipeline/errors/fix_plan.py`
- Test: `tests/test_pipeline_fix_plan.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_fix_plan.py
"""Tests for FIX-PLAN agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import FixPlan, ErrorAnalysis, ExhaustionItem
from wunderunner.pipeline.errors.fix_plan import run_fix_plan


@pytest.fixture
def error_analysis() -> ErrorAnalysis:
    """Sample error analysis."""
    return ErrorAnalysis(
        error_summary="Missing build script",
        root_cause="package.json has no build script",
        fix_history_review="No previous attempts",
        exhaustion_status=[],
        recommendation="continue",
        suggested_approach="Change CMD to use npm run dev",
    )


@pytest.fixture
def current_plan() -> str:
    """Current plan.md content."""
    return """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "build"]
```
"""


@pytest.mark.asyncio
async def test_run_fix_plan_returns_plan(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan returns FixPlan with updated Dockerfile."""
    mock_plan = FixPlan(
        summary="Change build command to dev",
        dockerfile="""FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]
""",
        changes_description="Changed CMD from 'npm run build' to 'npm run dev'",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=["MUST use node:20-slim"],
        )

    assert isinstance(result, FixPlan)
    assert "npm run dev" in result.dockerfile
    assert result.changes_description != ""


@pytest.mark.asyncio
async def test_run_fix_plan_honors_constraints(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan includes honored constraints."""
    constraints = ["MUST use node:20-slim", "MUST NOT use multi-stage"]

    mock_plan = FixPlan(
        summary="Fix",
        dockerfile="FROM node:20-slim\n",
        changes_description="Fixed",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=constraints,
        )

    assert result.constraints_honored == constraints
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_fix_plan.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write FIX-PLAN agent**

```python
# src/wunderunner/pipeline/errors/fix_plan.py
"""FIX-PLAN agent.

Generates surgical fix based on error analysis.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import FixPlan, ErrorAnalysis
from wunderunner.settings import get_model, Generation

SYSTEM_PROMPT = """\
You are generating a fix for a containerization error.

<input>
You receive:
1. Error analysis (diagnosis and suggested approach)
2. Current plan.md (what was tried)
3. Constraints (rules that MUST be honored)
</input>

<task>
Generate a surgical fix that:
1. Addresses the root cause from error analysis
2. Follows the suggested approach
3. Honors all constraints
4. Changes as little as possible
</task>

<output>
summary: Brief description of what this fix does
dockerfile: Complete updated Dockerfile content
compose: Updated docker-compose.yaml if needed (null if unchanged)
changes_description: What changed and why
constraints_honored: Echo back constraints that were honored
</output>

<critical_rules>
- Output COMPLETE file contents, not diffs
- Honor ALL constraints - they exist for a reason
- Make minimal changes - don't refactor unrelated code
- If the suggested approach conflicts with a constraint, find an alternative
</critical_rules>
"""


def _build_user_prompt(
    error_analysis: ErrorAnalysis,
    current_plan: str,
    constraints: list[str],
) -> str:
    """Build user prompt from error analysis and current plan."""
    parts = []

    # Error analysis
    parts.append("## Error Analysis\n")
    parts.append(f"**Summary:** {error_analysis.error_summary}")
    parts.append(f"**Root Cause:** {error_analysis.root_cause}")
    parts.append(f"**Suggested Approach:** {error_analysis.suggested_approach or 'None'}")
    parts.append("")

    # Current plan
    parts.append("## Current Plan\n")
    parts.append(current_plan)
    parts.append("")

    # Constraints
    parts.append("## Constraints (MUST honor)\n")
    if constraints:
        for c in constraints:
            parts.append(f"- {c}")
    else:
        parts.append("None")

    return "\n".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=FixPlan,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def run_fix_plan(
    project_dir: Path,
    error_analysis: ErrorAnalysis,
    current_plan: str,
    constraints: list[str],
) -> FixPlan:
    """Run FIX-PLAN phase.

    Args:
        project_dir: Project root directory.
        error_analysis: Analysis from ERROR-RESEARCH phase.
        current_plan: Content of current plan.md.
        constraints: Active constraints to honor.

    Returns:
        FixPlan with updated file contents.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(error_analysis, current_plan, constraints)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_fix_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/fix_plan.py tests/test_pipeline_fix_plan.py
git commit -m "feat(pipeline): add FIX-PLAN agent"
```

---

### Task 5.5: Add error-analysis artifact writer

**Files:**
- Modify: `src/wunderunner/pipeline/artifacts.py`
- Modify: `tests/test_pipeline_artifacts.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_artifacts.py (append)

from wunderunner.pipeline.models import ErrorAnalysis, ExhaustionItem, FixPlan
from wunderunner.pipeline.artifacts import write_error_analysis, write_fix_plan


@pytest.mark.asyncio
async def test_write_error_analysis(tmp_path: Path):
    """write_error_analysis creates error-analysis.md."""
    analysis = ErrorAnalysis(
        error_summary="Build failed",
        root_cause="Missing dependency",
        fix_history_review="1 attempt",
        exhaustion_status=[ExhaustionItem(approach="Add dep", attempted=False)],
        recommendation="continue",
        suggested_approach="Add pandas to requirements",
    )

    path = await write_error_analysis(tmp_path, analysis, attempt=2)

    assert path.exists()
    content = path.read_text()
    assert "Build failed" in content
    assert "Missing dependency" in content


@pytest.mark.asyncio
async def test_write_fix_plan(tmp_path: Path):
    """write_fix_plan creates fix-plan.md."""
    plan = FixPlan(
        summary="Add missing dependency",
        dockerfile="FROM python:3.11\nRUN pip install pandas\n",
        changes_description="Added pandas",
        constraints_honored=["MUST use python:3.11"],
    )

    path = await write_fix_plan(tmp_path, plan)

    assert path.exists()
    content = path.read_text()
    assert "Add missing dependency" in content
    assert "pip install pandas" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_artifacts.py::test_write_error_analysis -v`
Expected: FAIL with "cannot import name 'write_error_analysis'"

**Step 3: Add error artifact writers**

```python
# src/wunderunner/pipeline/artifacts.py (append)


async def write_error_analysis(
    project_dir: Path, analysis: ErrorAnalysis, attempt: int
) -> Path:
    """Write error-analysis.md artifact.

    Args:
        project_dir: Project root directory.
        analysis: ErrorAnalysis from ERROR-RESEARCH phase.
        attempt: Current attempt number.

    Returns:
        Path to written file.
    """
    content = _format_error_analysis(analysis, attempt)
    path = get_artifact_path(project_dir, "error-analysis.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_error_analysis(analysis: ErrorAnalysis, attempt: int) -> str:
    """Format ErrorAnalysis as markdown."""
    sections = [f"# Error Analysis (Attempt {attempt})\n"]

    sections.append(f"## Error Summary\n{analysis.error_summary}\n")
    sections.append(f"## Root Cause\n{analysis.root_cause}\n")
    sections.append(f"## Fix History Review\n{analysis.fix_history_review}\n")

    sections.append("## Exhaustion Status\n")
    for item in analysis.exhaustion_status:
        status = "[x]" if item.attempted else "[ ]"
        sections.append(f"- {status} {item.approach}")
    sections.append("")

    sections.append(f"**Recommendation:** {analysis.recommendation}\n")

    if analysis.suggested_approach:
        sections.append(f"## Suggested Approach\n{analysis.suggested_approach}\n")

    return "\n".join(sections)


async def write_fix_plan(project_dir: Path, plan: FixPlan) -> Path:
    """Write fix-plan.md artifact.

    Args:
        project_dir: Project root directory.
        plan: FixPlan from FIX-PLAN phase.

    Returns:
        Path to written file.
    """
    content = _format_fix_plan(plan)
    path = get_artifact_path(project_dir, "fix-plan.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_fix_plan(plan: FixPlan) -> str:
    """Format FixPlan as markdown."""
    sections = ["# Fix Plan\n"]

    sections.append(f"## Summary\n{plan.summary}\n")
    sections.append(f"## Changes\n{plan.changes_description}\n")

    if plan.constraints_honored:
        sections.append("## Constraints Honored\n")
        for c in plan.constraints_honored:
            sections.append(f"- [x] {c}")
        sections.append("")

    sections.append("## Updated Dockerfile\n```dockerfile")
    sections.append(plan.dockerfile)
    sections.append("```\n")

    if plan.compose:
        sections.append("## Updated docker-compose.yaml\n```yaml")
        sections.append(plan.compose)
        sections.append("```\n")

    return "\n".join(sections)
```

**Step 4: Add imports at top of artifacts.py**

```python
# At top of src/wunderunner/pipeline/artifacts.py, update imports:
from wunderunner.pipeline.models import (
    ResearchResult,
    ContainerizationPlan,
    FixHistory,
    ErrorAnalysis,
    FixPlan,
)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_artifacts.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/artifacts.py tests/test_pipeline_artifacts.py
git commit -m "feat(pipeline): add error analysis artifact writers"
```

---

**Part 5 Complete.** Error handling with constraint management, ERROR-RESEARCH, and FIX-PLAN. Next: Part 6 (CLI Integration).
## Part 6: CLI Integration

Wire up the pipeline to the CLI with feature flag and caching.

---

### Task 6.1: Add pipeline runner

**Files:**
- Create: `src/wunderunner/pipeline/runner.py`
- Test: `tests/test_pipeline_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_runner.py
"""Tests for main pipeline runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline.runner import run_pipeline, PipelineResult, PipelineStatus
from wunderunner.pipeline.models import (
    ResearchResult,
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
    ContainerizationPlan,
    ImplementResult,
)


@pytest.fixture
def mock_research_result() -> ResearchResult:
    """Mock research result."""
    return ResearchResult(
        runtime=RuntimeFindings(language="python", version="3.11"),
        dependencies=DependencyFindings(package_manager="pip"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )


@pytest.fixture
def mock_plan() -> ContainerizationPlan:
    """Mock plan."""
    return ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11\n",
        verification=[],
        reasoning="Simple",
        constraints_honored=[],
    )


@pytest.mark.asyncio
async def test_run_pipeline_success(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline returns success on happy path."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock) as mock_r:
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock) as mock_p:
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_r.return_value = mock_research_result
                mock_p.return_value = mock_plan
                mock_i.return_value = ImplementResult(success=True, files_written=["Dockerfile"])

                result = await run_pipeline(tmp_path)

    assert isinstance(result, PipelineResult)
    assert result.status == PipelineStatus.SUCCESS
    assert "Dockerfile" in result.files_written


@pytest.mark.asyncio
async def test_run_pipeline_retries_on_failure(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline retries when implement fails."""
    # First implement fails, second succeeds
    impl_results = [
        ImplementResult(success=False, phase="BUILD", error="Failed"),
        ImplementResult(success=True, files_written=["Dockerfile"]),
    ]
    impl_call_count = 0

    async def mock_implement(*args, **kwargs):
        nonlocal impl_call_count
        result = impl_results[impl_call_count]
        impl_call_count += 1
        return result

    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", side_effect=mock_implement):
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    with patch("wunderunner.pipeline.runner.run_fix_plan", new_callable=AsyncMock) as mock_fp:
                        from wunderunner.pipeline.models import ErrorAnalysis, FixPlan
                        mock_er.return_value = ErrorAnalysis(
                            error_summary="e", root_cause="r",
                            fix_history_review="f", recommendation="continue",
                        )
                        mock_fp.return_value = FixPlan(
                            summary="s", dockerfile="FROM x\n",
                            changes_description="c", constraints_honored=[],
                        )

                        result = await run_pipeline(tmp_path, max_attempts=3)

    assert result.status == PipelineStatus.SUCCESS
    assert impl_call_count == 2


@pytest.mark.asyncio
async def test_run_pipeline_stops_on_max_attempts(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline stops after max_attempts."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=False, phase="BUILD", error="Fail")
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    with patch("wunderunner.pipeline.runner.run_fix_plan", new_callable=AsyncMock) as mock_fp:
                        from wunderunner.pipeline.models import ErrorAnalysis, FixPlan
                        mock_er.return_value = ErrorAnalysis(
                            error_summary="e", root_cause="r",
                            fix_history_review="f", recommendation="continue",
                        )
                        mock_fp.return_value = FixPlan(
                            summary="s", dockerfile="FROM x\n",
                            changes_description="c", constraints_honored=[],
                        )

                        result = await run_pipeline(tmp_path, max_attempts=2)

    assert result.status == PipelineStatus.MAX_ATTEMPTS
    assert result.error is not None


@pytest.mark.asyncio
async def test_run_pipeline_stops_on_exhaustion(tmp_path: Path, mock_research_result, mock_plan):
    """run_pipeline stops when error research says stop."""
    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock, return_value=mock_research_result):
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock, return_value=mock_plan):
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=False, phase="BUILD", error="Fail")
                with patch("wunderunner.pipeline.runner.run_error_research", new_callable=AsyncMock) as mock_er:
                    from wunderunner.pipeline.models import ErrorAnalysis
                    mock_er.return_value = ErrorAnalysis(
                        error_summary="e", root_cause="r",
                        fix_history_review="f", recommendation="stop",  # Says stop!
                    )

                    result = await run_pipeline(tmp_path, max_attempts=5)

    assert result.status == PipelineStatus.EXHAUSTED
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write pipeline runner**

```python
# src/wunderunner/pipeline/runner.py
"""Main pipeline runner - orchestrates RESEARCH → PLAN → IMPLEMENT cycle."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from wunderunner.pipeline.artifacts import (
    write_research,
    read_research,
    write_plan,
    read_plan,
    write_fix_history,
    read_fix_history,
    write_error_analysis,
    write_fix_plan,
    get_artifact_path,
)
from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    FixError,
    ImplementResult,
)
from wunderunner.pipeline.research import run_research
from wunderunner.pipeline.plan import run_plan
from wunderunner.pipeline.implement import run_implement
from wunderunner.pipeline.errors import (
    run_error_research,
    run_fix_plan,
    update_constraints,
    increment_success_counts,
    derive_constraint,
)


class PipelineStatus(str, Enum):
    """Final status of pipeline run."""

    SUCCESS = "success"
    MAX_ATTEMPTS = "max_attempts"
    EXHAUSTED = "exhausted"
    ERROR = "error"


@dataclass
class PipelineResult:
    """Result of pipeline run."""

    status: PipelineStatus
    files_written: list[str]
    attempts: int
    error: str | None = None


ProgressCallback = Callable[[str, str], None]


async def run_pipeline(
    project_dir: Path,
    max_attempts: int = 5,
    rebuild: bool = False,
    replan: bool = False,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the RESEARCH → PLAN → IMPLEMENT pipeline.

    Args:
        project_dir: Project root directory.
        max_attempts: Maximum fix attempts before giving up.
        rebuild: Force re-run RESEARCH phase.
        replan: Force re-run PLAN phase.
        on_progress: Optional callback for progress updates.

    Returns:
        PipelineResult with final status.
    """

    def progress(phase: str, message: str) -> None:
        if on_progress:
            on_progress(phase, message)

    try:
        # Initialize or load fix history
        fix_history = await read_fix_history(project_dir)
        if not fix_history:
            fix_history = FixHistory(project=project_dir.name)

        # RESEARCH phase
        research_path = get_artifact_path(project_dir, "research.md")
        if rebuild or not research_path.exists():
            progress("RESEARCH", "Running project analysis...")
            research_result = await run_research(project_dir)
            await write_research(project_dir, research_result)
            progress("RESEARCH", "Complete")

        # PLAN phase
        plan_path = get_artifact_path(project_dir, "plan.md")
        if rebuild or replan or not plan_path.exists():
            progress("PLAN", "Generating containerization plan...")
            await run_plan(project_dir)
            progress("PLAN", "Complete")

        # IMPLEMENT phase with retry loop
        attempt = 0
        last_error: str | None = None
        files_written: list[str] = []

        while attempt < max_attempts:
            attempt += 1
            progress("IMPLEMENT", f"Attempt {attempt}/{max_attempts}")

            impl_result = await run_implement(project_dir, attempt=attempt)

            if impl_result.success:
                # Success! Update constraints and return
                fix_history = increment_success_counts(fix_history)
                await write_fix_history(project_dir, fix_history)

                progress("IMPLEMENT", "Success!")
                return PipelineResult(
                    status=PipelineStatus.SUCCESS,
                    files_written=impl_result.files_written,
                    attempts=attempt,
                )

            # Failed - run error handling cycle
            last_error = impl_result.error
            files_written = impl_result.files_written

            progress("ERROR-RESEARCH", "Analyzing error...")
            research_content = await read_research(project_dir)
            plan_content = await read_plan(project_dir)

            error_context = {
                "phase": impl_result.phase,
                "error": impl_result.error,
                "log_path": impl_result.logs,
            }

            error_analysis = await run_error_research(
                project_dir=project_dir,
                error_context=error_context,
                research_content=research_content,
                fix_history=fix_history,
            )
            await write_error_analysis(project_dir, error_analysis, attempt)

            # Check if we should stop
            if error_analysis.recommendation == "stop":
                progress("ERROR-RESEARCH", "All approaches exhausted")
                return PipelineResult(
                    status=PipelineStatus.EXHAUSTED,
                    files_written=files_written,
                    attempts=attempt,
                    error=last_error,
                )

            # Generate fix plan
            progress("FIX-PLAN", "Generating fix...")
            constraints = [
                c.rule for c in fix_history.active_constraints
                if c.status.value == "hard"
            ]

            fix_plan = await run_fix_plan(
                project_dir=project_dir,
                error_analysis=error_analysis,
                current_plan=plan_content,
                constraints=constraints,
            )
            await write_fix_plan(project_dir, fix_plan)

            # Record attempt
            fix_attempt = FixAttempt(
                attempt=attempt,
                phase=impl_result.phase or "UNKNOWN",
                error=FixError(
                    type=impl_result.phase or "unknown",
                    message=impl_result.error or "Unknown error",
                ),
                diagnosis=error_analysis.root_cause,
                outcome="failure",
            )
            fix_history.attempts.append(fix_attempt)

            # Update plan.md with fix plan content
            from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep
            updated_plan = ContainerizationPlan(
                summary=fix_plan.summary,
                dockerfile=fix_plan.dockerfile,
                compose=fix_plan.compose,
                verification=[],  # Keep original verification
                reasoning=fix_plan.changes_description,
                constraints_honored=fix_plan.constraints_honored,
            )
            await write_plan(project_dir, updated_plan)
            await write_fix_history(project_dir, fix_history)

            progress("FIX-PLAN", "Fix generated, retrying...")

        # Exceeded max attempts
        return PipelineResult(
            status=PipelineStatus.MAX_ATTEMPTS,
            files_written=files_written,
            attempts=attempt,
            error=last_error,
        )

    except Exception as e:
        return PipelineResult(
            status=PipelineStatus.ERROR,
            files_written=[],
            attempts=0,
            error=str(e),
        )
```

**Step 4: Update pipeline __init__.py**

```python
# src/wunderunner/pipeline/__init__.py
"""RESEARCH-PLAN-IMPLEMENT pipeline module."""

from wunderunner.pipeline.runner import run_pipeline, PipelineResult, PipelineStatus

__all__ = ["run_pipeline", "PipelineResult", "PipelineStatus"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/runner.py src/wunderunner/pipeline/__init__.py tests/test_pipeline_runner.py
git commit -m "feat(pipeline): add main pipeline runner"
```

---

### Task 6.2: Add CLI command

**Files:**
- Modify: `src/wunderunner/cli/main.py`
- Test: `tests/test_cli_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_pipeline.py
"""Tests for pipeline CLI command."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner

from wunderunner.cli.main import app
from wunderunner.pipeline.runner import PipelineResult, PipelineStatus


runner = CliRunner()


def test_containerize_v2_help():
    """containerize-v2 command shows help."""
    result = runner.invoke(app, ["containerize-v2", "--help"])
    assert result.exit_code == 0
    assert "RESEARCH" in result.stdout or "research" in result.stdout.lower()


def test_containerize_v2_requires_path():
    """containerize-v2 requires path argument."""
    result = runner.invoke(app, ["containerize-v2"])
    assert result.exit_code != 0


def test_containerize_v2_success(tmp_path: Path):
    """containerize-v2 reports success."""
    mock_result = PipelineResult(
        status=PipelineStatus.SUCCESS,
        files_written=["Dockerfile", "docker-compose.yaml"],
        attempts=1,
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = runner.invoke(app, ["containerize-v2", str(tmp_path)])

    assert result.exit_code == 0
    assert "Success" in result.stdout or "success" in result.stdout.lower()


def test_containerize_v2_failure(tmp_path: Path):
    """containerize-v2 reports failure."""
    mock_result = PipelineResult(
        status=PipelineStatus.MAX_ATTEMPTS,
        files_written=["Dockerfile"],
        attempts=5,
        error="Build failed",
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = runner.invoke(app, ["containerize-v2", str(tmp_path)])

    assert result.exit_code == 1
    assert "failed" in result.stdout.lower() or "error" in result.stdout.lower()


def test_containerize_v2_rebuild_flag(tmp_path: Path):
    """containerize-v2 --rebuild forces research."""
    mock_result = PipelineResult(
        status=PipelineStatus.SUCCESS,
        files_written=["Dockerfile"],
        attempts=1,
    )

    with patch(
        "wunderunner.cli.main.run_pipeline",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_run:
        result = runner.invoke(app, ["containerize-v2", str(tmp_path), "--rebuild"])

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("rebuild") is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_pipeline.py -v`
Expected: FAIL (command doesn't exist yet)

**Step 3: Add CLI command**

```python
# src/wunderunner/cli/main.py (add new command)

# Add import at top
from wunderunner.pipeline import run_pipeline, PipelineResult, PipelineStatus

# Add command after existing commands

@app.command("containerize-v2")
def containerize_v2(
    path: Annotated[
        Path,
        typer.Argument(help="Path to project directory"),
    ],
    rebuild: Annotated[
        bool,
        typer.Option("--rebuild", help="Force re-run RESEARCH phase"),
    ] = False,
    replan: Annotated[
        bool,
        typer.Option("--replan", help="Force re-run PLAN phase"),
    ] = False,
    max_attempts: Annotated[
        int,
        typer.Option("--max-attempts", help="Maximum fix attempts"),
    ] = 5,
) -> None:
    """Containerize a project using RESEARCH → PLAN → IMPLEMENT pipeline.

    This is the v2 pipeline with file-based artifacts and fresh context per phase.
    """
    import asyncio
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {path}[/red]")
        raise typer.Exit(1)

    def on_progress(phase: str, message: str) -> None:
        console.print(f"[cyan]{phase}[/cyan]: {message}")

    console.print(Panel(f"[bold]Containerizing[/bold] {path.name}", expand=False))

    result: PipelineResult = asyncio.run(
        run_pipeline(
            project_dir=path,
            max_attempts=max_attempts,
            rebuild=rebuild,
            replan=replan,
            on_progress=on_progress,
        )
    )

    if result.status == PipelineStatus.SUCCESS:
        console.print()
        console.print(Panel(
            f"[green]Success![/green]\n"
            f"Files: {', '.join(result.files_written)}\n"
            f"Attempts: {result.attempts}",
            title="Pipeline Complete",
            expand=False,
        ))
    else:
        console.print()
        console.print(Panel(
            f"[red]Failed[/red]: {result.status.value}\n"
            f"Error: {result.error}\n"
            f"Attempts: {result.attempts}",
            title="Pipeline Failed",
            expand=False,
        ))
        raise typer.Exit(1)
```

**Step 4: Add import for Annotated if needed**

```python
# At top of src/wunderunner/cli/main.py, ensure these imports exist:
from typing import Annotated
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_pipeline.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/cli/main.py tests/test_cli_pipeline.py
git commit -m "feat(cli): add containerize-v2 command"
```

---

### Task 6.3: Add cache invalidation logic

**Files:**
- Create: `src/wunderunner/pipeline/cache.py`
- Test: `tests/test_pipeline_cache.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_cache.py
"""Tests for cache invalidation."""

import pytest
from pathlib import Path
import time

from wunderunner.pipeline.cache import should_rebuild_research, should_replan


def test_should_rebuild_when_no_research(tmp_path: Path):
    """Should rebuild if research.md doesn't exist."""
    assert should_rebuild_research(tmp_path) is True


def test_should_not_rebuild_when_fresh(tmp_path: Path):
    """Should not rebuild if research.md is newer than manifest."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Research")

    # Create older manifest
    (tmp_path / "pyproject.toml").write_text("[project]")
    time.sleep(0.01)  # Ensure mtime difference
    (wunderunner_dir / "research.md").write_text("# Updated Research")

    assert should_rebuild_research(tmp_path) is False


def test_should_rebuild_when_manifest_changed(tmp_path: Path):
    """Should rebuild if manifest is newer than research.md."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Research")

    time.sleep(0.01)  # Ensure mtime difference
    (tmp_path / "pyproject.toml").write_text("[project]\n# changed")

    assert should_rebuild_research(tmp_path) is True


def test_should_replan_when_no_plan(tmp_path: Path):
    """Should replan if plan.md doesn't exist."""
    assert should_replan(tmp_path) is True


def test_should_replan_when_research_changed(tmp_path: Path):
    """Should replan if research.md is newer than plan.md."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "plan.md").write_text("# Plan")

    time.sleep(0.01)
    (wunderunner_dir / "research.md").write_text("# Updated Research")

    assert should_replan(tmp_path) is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_cache.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write cache module**

```python
# src/wunderunner/pipeline/cache.py
"""Cache invalidation logic for pipeline artifacts."""

from pathlib import Path

from wunderunner.pipeline.artifacts import get_artifact_path

# Files that trigger research invalidation
MANIFEST_FILES = [
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "requirements.txt",
]


def should_rebuild_research(project_dir: Path) -> bool:
    """Check if RESEARCH phase should re-run.

    Returns True if:
    - research.md doesn't exist
    - Any manifest file is newer than research.md

    Args:
        project_dir: Project root directory.

    Returns:
        True if research should be re-run.
    """
    research_path = get_artifact_path(project_dir, "research.md")

    if not research_path.exists():
        return True

    research_mtime = research_path.stat().st_mtime

    for manifest in MANIFEST_FILES:
        manifest_path = project_dir / manifest
        if manifest_path.exists():
            if manifest_path.stat().st_mtime > research_mtime:
                return True

    return False


def should_replan(project_dir: Path) -> bool:
    """Check if PLAN phase should re-run.

    Returns True if:
    - plan.md doesn't exist
    - research.md is newer than plan.md
    - fixes.json is newer than plan.md (constraints changed)

    Args:
        project_dir: Project root directory.

    Returns:
        True if plan should be re-generated.
    """
    plan_path = get_artifact_path(project_dir, "plan.md")

    if not plan_path.exists():
        return True

    plan_mtime = plan_path.stat().st_mtime

    # Check if research changed
    research_path = get_artifact_path(project_dir, "research.md")
    if research_path.exists() and research_path.stat().st_mtime > plan_mtime:
        return True

    # Check if constraints changed
    fixes_path = get_artifact_path(project_dir, "fixes.json")
    if fixes_path.exists() and fixes_path.stat().st_mtime > plan_mtime:
        return True

    return False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_cache.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/cache.py tests/test_pipeline_cache.py
git commit -m "feat(pipeline): add cache invalidation logic"
```

---

### Task 6.4: Integrate cache into runner

**Files:**
- Modify: `src/wunderunner/pipeline/runner.py`
- Modify: `tests/test_pipeline_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_runner.py (append)


@pytest.mark.asyncio
async def test_run_pipeline_uses_cache(tmp_path: Path, mock_plan):
    """run_pipeline skips research if cache valid."""
    # Create cached research
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("# Cached Research\n## Runtime\n- python")
    (wunderunner_dir / "plan.md").write_text("# Plan\n## Files\n### Dockerfile\n```dockerfile\nFROM x\n```")

    with patch("wunderunner.pipeline.runner.run_research", new_callable=AsyncMock) as mock_r:
        with patch("wunderunner.pipeline.runner.run_plan", new_callable=AsyncMock) as mock_p:
            with patch("wunderunner.pipeline.runner.run_implement", new_callable=AsyncMock) as mock_i:
                mock_i.return_value = ImplementResult(success=True, files_written=["Dockerfile"])

                result = await run_pipeline(tmp_path)

    # Research and plan should NOT be called (cache hit)
    mock_r.assert_not_called()
    mock_p.assert_not_called()
    assert result.status == PipelineStatus.SUCCESS
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_runner.py::test_run_pipeline_uses_cache -v`
Expected: FAIL (runner doesn't check cache yet)

**Step 3: Update runner to use cache**

```python
# src/wunderunner/pipeline/runner.py

# Add import at top
from wunderunner.pipeline.cache import should_rebuild_research, should_replan

# Replace the RESEARCH and PLAN sections in run_pipeline with:

        # RESEARCH phase (with cache)
        research_path = get_artifact_path(project_dir, "research.md")
        need_research = rebuild or should_rebuild_research(project_dir)

        if need_research:
            progress("RESEARCH", "Running project analysis...")
            research_result = await run_research(project_dir)
            await write_research(project_dir, research_result)
            progress("RESEARCH", "Complete")

        # PLAN phase (with cache)
        plan_path = get_artifact_path(project_dir, "plan.md")
        need_plan = rebuild or replan or should_replan(project_dir)

        if need_plan:
            progress("PLAN", "Generating containerization plan...")
            await run_plan(project_dir)
            progress("PLAN", "Complete")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/runner.py tests/test_pipeline_runner.py
git commit -m "feat(pipeline): add cache integration to runner"
```

---

### Task 6.5: Add integration test

**Files:**
- Create: `tests/test_pipeline_integration.py`

**Step 1: Write integration test**

```python
# tests/test_pipeline_integration.py
"""Integration tests for complete pipeline."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from wunderunner.pipeline import run_pipeline, PipelineStatus
from wunderunner.pipeline.models import (
    RuntimeFindings,
    DependencyFindings,
    ConfigFindings,
    ServiceFindings,
    ContainerizationPlan,
    VerificationStep,
)


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "testapp"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn"]
""")
    (tmp_path / "app.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""")
    (tmp_path / "uv.lock").write_text("# lock")
    return tmp_path


@pytest.mark.asyncio
async def test_full_pipeline_success(python_project: Path):
    """Test complete pipeline from research to success."""
    # Mock specialist agents to return expected data
    runtime = RuntimeFindings(language="python", version="3.11", framework="fastapi")
    deps = DependencyFindings(package_manager="uv", start_command="uvicorn app:app")
    config = ConfigFindings()
    services = ServiceFindings()

    plan = ContainerizationPlan(
        summary="Python FastAPI app",
        dockerfile="""FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0"]
""",
        verification=[
            VerificationStep(command="docker build -t app .", expected="exit 0"),
        ],
        reasoning="Standard FastAPI setup",
        constraints_honored=[],
    )

    # Mock all the agent runs
    with patch("wunderunner.pipeline.research.specialists.runtime.agent.run", new_callable=AsyncMock) as mock_rt:
        with patch("wunderunner.pipeline.research.specialists.dependencies.agent.run", new_callable=AsyncMock) as mock_dp:
            with patch("wunderunner.pipeline.research.specialists.config.agent.run", new_callable=AsyncMock) as mock_cf:
                with patch("wunderunner.pipeline.research.specialists.services.agent.run", new_callable=AsyncMock) as mock_sv:
                    with patch("wunderunner.pipeline.plan.agent.agent.run", new_callable=AsyncMock) as mock_pl:
                        with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
                            # Set up mocks
                            mock_rt.return_value = AsyncMock(output=runtime)
                            mock_dp.return_value = AsyncMock(output=deps)
                            mock_cf.return_value = AsyncMock(output=config)
                            mock_sv.return_value = AsyncMock(output=services)
                            mock_pl.return_value = AsyncMock(output=plan)

                            # Mock docker build success
                            proc = MagicMock()
                            proc.returncode = 0
                            proc.communicate = AsyncMock(return_value=(b"Built!", b""))
                            mock_proc.return_value = proc

                            # Run pipeline
                            result = await run_pipeline(python_project)

    # Verify result
    assert result.status == PipelineStatus.SUCCESS
    assert result.attempts == 1
    assert "Dockerfile" in result.files_written

    # Verify files were created
    assert (python_project / "Dockerfile").exists()
    assert (python_project / ".wunderunner" / "research.md").exists()
    assert (python_project / ".wunderunner" / "plan.md").exists()

    # Verify Dockerfile content
    dockerfile_content = (python_project / "Dockerfile").read_text()
    assert "FROM python:3.11-slim" in dockerfile_content
    assert "uvicorn" in dockerfile_content
```

**Step 2: Run test**

Run: `uv run pytest tests/test_pipeline_integration.py -v`
Expected: PASS (once all previous tasks complete)

**Step 3: Commit**

```bash
git add tests/test_pipeline_integration.py
git commit -m "test(pipeline): add integration test"
```

---

**Part 6 Complete.** CLI integration with cache and full pipeline runner.

---

## Final Steps

### Commit all changes

```bash
git add -A
git commit -m "feat(pipeline): complete RESEARCH → PLAN → IMPLEMENT pipeline"
```

### Run full test suite

```bash
uv run pytest tests/test_pipeline*.py -v
```

### Update CLAUDE.md with new command

Add to project CLAUDE.md:

```markdown
## Pipeline v2

New containerization pipeline with RESEARCH → PLAN → IMPLEMENT phases:

```bash
wxr containerize-v2 ./path/to/project
wxr containerize-v2 ./project --rebuild    # Force re-analyze
wxr containerize-v2 ./project --replan     # Force re-plan
wxr containerize-v2 ./project --max-attempts 10
```

Artifacts stored in `.wunderunner/`:
- `research.md` - Project analysis
- `plan.md` - Containerization plan with exact file contents
- `fixes.json` - Fix history and constraints
- `error-analysis.md` - Error diagnosis (when errors occur)
- `fix-plan.md` - Fix plan (when errors occur)
- `logs/` - Build/verification logs
```

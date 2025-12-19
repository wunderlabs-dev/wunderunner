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

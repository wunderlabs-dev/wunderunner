"""Tests for pipeline artifact models."""

from wunderunner.pipeline.models import (
    ConfigFindings,
    Constraint,
    ConstraintStatus,
    ContainerizationPlan,
    DependencyFindings,
    EnvVarFinding,
    FixAttempt,
    FixChange,
    FixError,
    FixHistory,
    NativeDependency,
    ResearchResult,
    RuntimeFindings,
    ServiceFinding,
    ServiceFindings,
    VerificationStep,
)


def test_runtime_findings_required_fields():
    """RuntimeFindings requires language."""
    findings = RuntimeFindings(language="python")
    assert findings.language == "python"
    assert findings.version is None
    assert findings.framework is None
    assert findings.entrypoint is None


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

"""Tests for pipeline artifact models."""

from wunderunner.pipeline.models import (
    ConfigFindings,
    DependencyFindings,
    EnvVarFinding,
    NativeDependency,
    RuntimeFindings,
    ServiceFinding,
    ServiceFindings,
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

"""Tests for pipeline artifact models."""

from wunderunner.pipeline.models import DependencyFindings, NativeDependency, RuntimeFindings


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

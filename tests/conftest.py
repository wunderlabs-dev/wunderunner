"""Shared test fixtures for integration tests."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wunderunner.models.analysis import (
    Analysis,
    BuildStrategy,
    CodeStyle,
    EnvVar,
    ProjectStructure,
    ServiceConfig,
)
from wunderunner.models.validation import GradeBreakdown, ValidationResult
from wunderunner.workflows.state import ContainerizeState, Learning, Phase, Severity


@pytest.fixture
def node_analysis() -> Analysis:
    """Create a minimal Node.js project analysis."""
    return Analysis(
        project_structure=ProjectStructure(
            runtime="node",
            framework="express",
            package_manager="npm",
            entry_point="index.js",
        ),
        build_strategy=BuildStrategy(
            build_command="npm run build",
            start_command="npm start",
        ),
        code_style=CodeStyle(uses_typescript=False),
        env_vars=[],
    )


@pytest.fixture
def python_analysis() -> Analysis:
    """Create a minimal Python project analysis."""
    return Analysis(
        project_structure=ProjectStructure(
            runtime="python",
            framework="fastapi",
            package_manager="pip",
            entry_point="app.py",
        ),
        build_strategy=BuildStrategy(
            build_command=None,
            start_command="uvicorn app:app --host 0.0.0.0",
        ),
        code_style=CodeStyle(),
        env_vars=[],
    )


@pytest.fixture
def analysis_with_secrets() -> Analysis:
    """Create analysis with secret env vars."""
    return Analysis(
        project_structure=ProjectStructure(
            runtime="node",
            framework="express",
            package_manager="npm",
            entry_point="index.js",
        ),
        build_strategy=BuildStrategy(
            start_command="npm start",
        ),
        code_style=CodeStyle(),
        env_vars=[
            EnvVar(name="DATABASE_URL", secret=True, service="postgres"),
            EnvVar(name="API_KEY", secret=True),
            EnvVar(name="PORT", required=False, default="3000"),
        ],
    )


@pytest.fixture
def analysis_with_services() -> Analysis:
    """Create analysis with confirmed services."""
    return Analysis(
        project_structure=ProjectStructure(
            runtime="node",
            framework="express",
            package_manager="npm",
            entry_point="index.js",
        ),
        build_strategy=BuildStrategy(
            start_command="npm start",
        ),
        code_style=CodeStyle(),
        env_vars=[
            EnvVar(name="DATABASE_URL", service="postgres"),
            EnvVar(name="REDIS_URL", service="redis"),
        ],
        services=[
            ServiceConfig(type="postgres", env_vars=["DATABASE_URL"]),
            ServiceConfig(type="redis", env_vars=["REDIS_URL"]),
        ],
    )


@pytest.fixture
def valid_dockerfile() -> str:
    """Return a valid minimal Dockerfile."""
    return """FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
"""


@pytest.fixture
def invalid_dockerfile() -> str:
    """Return an invalid Dockerfile (missing FROM)."""
    return """WORKDIR /app
COPY . .
CMD ["npm", "start"]
"""


@pytest.fixture
def valid_compose() -> str:
    """Return a valid docker-compose.yaml."""
    return """version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
"""


@pytest.fixture
def passing_validation() -> ValidationResult:
    """Return a passing validation result."""
    return ValidationResult(
        is_valid=True,
        grade=85,
        breakdown=GradeBreakdown(
            secrets=30,
            runtime=20,
            package_manager=15,
            source_copy=10,
            base_image=5,
            simplicity=5,
        ),
        feedback="Good Dockerfile with proper layering",
        issues=[],
        recommendations=[],
    )


@pytest.fixture
def failing_validation() -> ValidationResult:
    """Return a failing validation result."""
    return ValidationResult(
        is_valid=False,
        grade=45,
        breakdown=GradeBreakdown(
            secrets=0,
            runtime=15,
            package_manager=10,
            source_copy=10,
            base_image=5,
            simplicity=5,
        ),
        feedback="Missing secret handling",
        issues=["Secrets not properly handled with ARG/ENV"],
        recommendations=["Add ARG for each secret", "Use ENV to expose secrets"],
    )


@pytest.fixture
def build_learning() -> Learning:
    """Create a learning from a build failure."""
    return Learning(
        phase=Phase.BUILD,
        error_type="BuildError",
        error_message="npm ERR! Missing script: build",
        context="package.json has no build script",
    )


@pytest.fixture
def validation_learning() -> Learning:
    """Create a learning from a validation failure."""
    return Learning(
        phase=Phase.VALIDATION,
        error_type="ValidationFailed",
        error_message="Grade: 45/100. Secrets not properly handled",
    )


@pytest.fixture
def progress_messages() -> list[tuple[Severity, str]]:
    """Collector for progress callback messages."""
    return []


@pytest.fixture
def mock_progress(progress_messages):
    """Create a progress callback that collects messages."""
    def _progress(severity: Severity, message: str) -> None:
        progress_messages.append((severity, message))
    return _progress


@pytest.fixture
def workflow_state(tmp_path, mock_progress) -> ContainerizeState:
    """Create a ContainerizeState for testing."""
    return ContainerizeState(
        path=tmp_path,
        rebuild=False,
        on_progress=mock_progress,
    )

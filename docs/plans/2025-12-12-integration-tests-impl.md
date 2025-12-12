# Integration Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement comprehensive integration tests for wunderunner's activities and workflow to validate the containerization pipeline end-to-end.

**Architecture:** Create a shared test fixtures module (conftest.py) with mock factories for Analysis, Docker client, and agent responses. Build integration tests that validate activity orchestration with mocked LLM agents but real logic flows. Use pytest-asyncio for async tests, tmp_path for file I/O.

**Tech Stack:** pytest, pytest-asyncio, unittest.mock (AsyncMock, MagicMock, patch)

---

## Task 1: Create Shared Test Fixtures (conftest.py)

**Files:**
- Create: `tests/conftest.py`

**Step 1: Write the fixture file with core fixtures**

```python
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
```

**Step 2: Verify fixtures load correctly**

Run: `uv run pytest tests/conftest.py --collect-only`
Expected: No errors, pytest collects the conftest

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared fixtures for integration tests"
```

---

## Task 2: Workflow State Tests Enhancement

**Files:**
- Modify: `tests/test_workflow_state.py`

**Step 1: Write additional tests for state mutations**

Add these tests to the existing file:

```python
"""Tests for workflow state."""

import pytest

from wunderunner.workflows.state import (
    ContainerizeState,
    Learning,
    Phase,
    Severity,
    _noop_hint_prompt,
    _noop_progress,
    _noop_secret_prompt,
    _noop_service_prompt,
)


class TestContainerizeState:
    """Tests for ContainerizeState dataclass."""

    def test_state_creation_minimal(self, tmp_path):
        """State can be created with just path."""
        state = ContainerizeState(path=tmp_path)
        assert state.path == tmp_path
        assert state.rebuild is False
        assert state.analysis is None
        assert state.learnings == []
        assert state.hints == []
        assert state.retry_count == 0

    def test_state_learning_accumulation(self, tmp_path):
        """Learnings accumulate correctly."""
        state = ContainerizeState(path=tmp_path)

        learning1 = Learning(
            phase=Phase.BUILD,
            error_type="BuildError",
            error_message="Build failed",
        )
        learning2 = Learning(
            phase=Phase.HEALTHCHECK,
            error_type="HealthcheckError",
            error_message="Timeout",
        )

        state.learnings.append(learning1)
        state.learnings.append(learning2)

        assert len(state.learnings) == 2
        assert state.learnings[0].phase == Phase.BUILD
        assert state.learnings[1].phase == Phase.HEALTHCHECK

    def test_state_hint_accumulation(self, tmp_path):
        """Hints accumulate correctly."""
        state = ContainerizeState(path=tmp_path)

        state.hints.append("Try using node:20-slim")
        state.hints.append("Add npm ci instead of npm install")

        assert len(state.hints) == 2

    def test_state_secret_values_stored(self, tmp_path):
        """Secret values are stored in dict."""
        state = ContainerizeState(path=tmp_path)

        state.secret_values["DATABASE_URL"] = "postgres://localhost/db"
        state.secret_values["API_KEY"] = "secret123"

        assert state.secret_values["DATABASE_URL"] == "postgres://localhost/db"
        assert state.secret_values["API_KEY"] == "secret123"

    def test_state_dockerfile_messages_stored(self, tmp_path):
        """Message history for Dockerfile generation is stored."""
        state = ContainerizeState(path=tmp_path)

        state.dockerfile_messages = [{"role": "user", "content": "test"}]

        assert len(state.dockerfile_messages) == 1

    def test_state_retry_count_increments(self, tmp_path):
        """Retry count can be incremented."""
        state = ContainerizeState(path=tmp_path)

        assert state.retry_count == 0
        state.retry_count += 1
        assert state.retry_count == 1


class TestDefaultCallbacks:
    """Tests for default callback implementations."""

    def test_noop_progress_does_nothing(self):
        """Default progress callback is silent."""
        # Should not raise
        _noop_progress(Severity.INFO, "test message")
        _noop_progress(Severity.ERROR, "error message")

    def test_noop_secret_prompt_raises(self):
        """Default secret prompt raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="not provided"):
            _noop_secret_prompt("API_KEY", None)

    def test_noop_hint_prompt_returns_none(self):
        """Default hint prompt returns None (quit)."""
        result = _noop_hint_prompt([])
        assert result is None

    def test_noop_service_prompt_auto_confirms(self):
        """Default service prompt auto-confirms all services."""
        result = _noop_service_prompt("postgres", ["DATABASE_URL"])
        assert result is True


class TestLearning:
    """Tests for Learning dataclass."""

    def test_learning_minimal(self):
        """Learning can be created with required fields."""
        learning = Learning(
            phase=Phase.BUILD,
            error_type="BuildError",
            error_message="npm install failed",
        )
        assert learning.phase == Phase.BUILD
        assert learning.context is None

    def test_learning_with_context(self):
        """Learning can include context."""
        learning = Learning(
            phase=Phase.HEALTHCHECK,
            error_type="HealthcheckError",
            error_message="Container exited",
            context="Exit code 1, logs: ModuleNotFoundError",
        )
        assert learning.context is not None
        assert "ModuleNotFoundError" in learning.context
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_state.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_workflow_state.py
git commit -m "test: enhance workflow state tests with mutation and callback tests"
```

---

## Task 3: Validation Activity Integration Test

**Files:**
- Create: `tests/test_activity_validation.py`

**Step 1: Write the failing test for two-tier validation**

```python
"""Integration tests for validation activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import validation
from wunderunner.exceptions import ValidationError
from wunderunner.models.validation import GradeBreakdown, ValidationResult


class TestValidateActivity:
    """Integration tests for validation.validate()."""

    @pytest.mark.asyncio
    async def test_invalid_syntax_fails_fast(self, node_analysis, invalid_dockerfile):
        """Tier 1: Invalid syntax fails without calling LLM."""
        # invalid_dockerfile is missing FROM
        with patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent:
            result = await validation.validate(
                invalid_dockerfile,
                node_analysis,
                learnings=[],
            )

            # Should fail programmatic validation
            assert result.is_valid is False
            assert result.grade == 0
            assert "FROM" in str(result.issues) or len(result.issues) > 0

            # LLM agent should NOT be called
            mock_agent.agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_syntax_calls_llm_grader(
        self, node_analysis, valid_dockerfile, passing_validation
    ):
        """Tier 2: Valid syntax proceeds to LLM grading."""
        mock_result = MagicMock()
        mock_result.output = passing_validation

        with (
            patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.validation.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await validation.validate(
                valid_dockerfile,
                node_analysis,
                learnings=[],
            )

            # LLM agent SHOULD be called
            mock_agent.agent.run.assert_called_once()

            # Result should come from LLM
            assert result.is_valid is True
            assert result.grade == 85

    @pytest.mark.asyncio
    async def test_grade_below_80_is_invalid(self, node_analysis, valid_dockerfile):
        """Grade below 80 marks result as invalid."""
        mock_validation = ValidationResult(
            is_valid=True,  # Agent might return True
            grade=75,
            breakdown=GradeBreakdown(),
            feedback="Needs improvement",
            issues=[],
            recommendations=["Add multi-stage build"],
        )
        mock_result = MagicMock()
        mock_result.output = mock_validation

        with (
            patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.validation.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await validation.validate(
                valid_dockerfile,
                node_analysis,
                learnings=[],
            )

            # Activity overrides agent's is_valid based on grade
            assert result.is_valid is False
            assert result.grade == 75

    @pytest.mark.asyncio
    async def test_grade_80_or_above_is_valid(self, node_analysis, valid_dockerfile):
        """Grade >= 80 marks result as valid."""
        mock_validation = ValidationResult(
            is_valid=False,  # Agent might return False
            grade=80,
            breakdown=GradeBreakdown(),
            feedback="Acceptable",
            issues=[],
            recommendations=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_validation

        with (
            patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.validation.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await validation.validate(
                valid_dockerfile,
                node_analysis,
                learnings=[],
            )

            # Activity overrides agent's is_valid based on grade
            assert result.is_valid is True
            assert result.grade == 80

    @pytest.mark.asyncio
    async def test_agent_error_raises_validation_error(
        self, node_analysis, valid_dockerfile
    ):
        """Agent failure raises ValidationError."""
        with (
            patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.validation.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API timeout"))

            with pytest.raises(ValidationError, match="Failed to validate"):
                await validation.validate(
                    valid_dockerfile,
                    node_analysis,
                    learnings=[],
                )

    @pytest.mark.asyncio
    async def test_secrets_validation_requires_arg_env(self, analysis_with_secrets):
        """Dockerfile without ARG/ENV for secrets fails programmatic check."""
        dockerfile_without_secrets = """FROM node:20-slim
WORKDIR /app
COPY . .
CMD ["npm", "start"]
"""
        result = await validation.validate(
            dockerfile_without_secrets,
            analysis_with_secrets,
            learnings=[],
        )

        # Should fail because secrets (DATABASE_URL, API_KEY) not handled
        assert result.is_valid is False
        assert result.grade == 0
        # Issues should mention missing ARG
        issues_text = " ".join(result.issues)
        assert "ARG" in issues_text or "DATABASE_URL" in issues_text

    @pytest.mark.asyncio
    async def test_invalid_result_populates_issues_from_recommendations(
        self, node_analysis, valid_dockerfile
    ):
        """When invalid and no issues, populate from recommendations."""
        mock_validation = ValidationResult(
            is_valid=False,
            grade=60,
            breakdown=GradeBreakdown(),
            feedback="Needs work",
            issues=[],  # Empty issues
            recommendations=["Use npm ci instead of npm install"],
        )
        mock_result = MagicMock()
        mock_result.output = mock_validation

        with (
            patch("wunderunner.activities.validation.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.validation.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await validation.validate(
                valid_dockerfile,
                node_analysis,
                learnings=[],
            )

            # Issues should be populated from recommendations
            assert len(result.issues) > 0
            assert "npm ci" in result.issues[0]
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_activity_validation.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_activity_validation.py
git commit -m "test: add integration tests for validation activity"
```

---

## Task 4: Dockerfile Generation Activity Integration Test

**Files:**
- Create: `tests/test_activity_dockerfile.py`

**Step 1: Write the failing tests for dockerfile generation**

```python
"""Integration tests for dockerfile generation activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import dockerfile
from wunderunner.exceptions import DockerfileError
from wunderunner.models.generation import DockerfileResult
from wunderunner.workflows.state import Learning, Phase


class TestGenerateActivity:
    """Integration tests for dockerfile.generate()."""

    @pytest.mark.asyncio
    async def test_fresh_generation_returns_dockerfile(self, node_analysis, tmp_path):
        """Fresh generation returns valid GenerateResult."""
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nWORKDIR /app\n",
            confidence=8,
            reasoning="Standard Node.js setup",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = [{"role": "assistant", "content": "..."}]

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            assert result.result.dockerfile == "FROM node:20-slim\nWORKDIR /app\n"
            assert result.result.confidence == 8
            assert len(result.messages) > 0

    @pytest.mark.asyncio
    async def test_refinement_uses_existing_dockerfile(self, node_analysis, tmp_path):
        """Refinement passes existing Dockerfile to agent."""
        existing = "FROM node:18-slim\nWORKDIR /app\n"
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nWORKDIR /app\n",
            confidence=9,
            reasoning="Upgraded to Node 20",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=existing,
                project_path=tmp_path,
            )

            # Verify existing was passed to prompt render
            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("existing_dockerfile") == existing

    @pytest.mark.asyncio
    async def test_learnings_passed_to_agent(self, node_analysis, tmp_path):
        """Learnings from previous attempts are passed to agent."""
        learnings = [
            Learning(
                phase=Phase.BUILD,
                error_type="BuildError",
                error_message="npm ERR! Missing script",
            )
        ]
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=7,
            reasoning="Fixed build script issue",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                node_analysis,
                learnings=learnings,
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("learnings") == learnings

    @pytest.mark.asyncio
    async def test_hints_passed_to_agent(self, node_analysis, tmp_path):
        """User hints are passed to agent."""
        hints = ["Use node:20-slim as base image"]
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=9,
            reasoning="Used suggested base image",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=hints,
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("hints") == hints

    @pytest.mark.asyncio
    async def test_message_history_preserved(self, node_analysis, tmp_path):
        """Message history is passed and updated for stateful conversation."""
        previous_messages = [{"role": "user", "content": "previous"}]
        new_messages = [{"role": "assistant", "content": "new response"}]

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=8,
            reasoning="Continued conversation",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = new_messages

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
                message_history=previous_messages,
            )

            # Verify history was passed to agent
            call_kwargs = mock_agent.agent.run.call_args.kwargs
            assert call_kwargs.get("message_history") == previous_messages

            # Verify new messages returned
            assert result.messages == new_messages

    @pytest.mark.asyncio
    async def test_agent_error_raises_dockerfile_error(self, node_analysis, tmp_path):
        """Agent failure raises DockerfileError."""
        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API timeout"))
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            with pytest.raises(DockerfileError, match="Failed to generate"):
                await dockerfile.generate(
                    node_analysis,
                    learnings=[],
                    hints=[],
                    existing=None,
                    project_path=tmp_path,
                )

    @pytest.mark.asyncio
    async def test_secrets_extracted_from_analysis(self, analysis_with_secrets, tmp_path):
        """Secrets are extracted and passed to agent prompt."""
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nARG DATABASE_URL\nARG API_KEY\n",
            confidence=8,
            reasoning="Added secret ARGs",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                analysis_with_secrets,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            secrets = call_kwargs.get("secrets", [])
            secret_names = [s.name for s in secrets]
            assert "DATABASE_URL" in secret_names
            assert "API_KEY" in secret_names
            # PORT is not a secret
            assert "PORT" not in secret_names


class TestRegressionCheck:
    """Tests for regression detection during generation."""

    @pytest.mark.asyncio
    async def test_regression_detected_adjusts_confidence(self, node_analysis, tmp_path):
        """Regression detection lowers confidence and adds warning."""
        from wunderunner.agents.validation.regression import RegressionResult
        from wunderunner.models.context import ContextEntry, EntryType

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:18-slim\n",  # Old version
            confidence=8,
            reasoning="Generated dockerfile",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        mock_regression = RegressionResult(
            has_regression=True,
            violations=["Reverted to node:18 from node:20"],
            adjusted_confidence=4,
        )
        mock_regression_result = MagicMock()
        mock_regression_result.output = mock_regression

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            fix="Upgraded to node:20-slim",
            explanation="Node 20 required for ESM support",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]
        mock_context.violation_count = 0

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.regression_agent") as mock_reg_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.activities.dockerfile.save_context", new_callable=AsyncMock),
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            mock_reg_agent.USER_PROMPT.render.return_value = "regression prompt"
            mock_reg_agent.agent.run = AsyncMock(return_value=mock_regression_result)

            mock_load.return_value = mock_context

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            # Confidence should be lowered
            assert result.result.confidence == 4
            # Reasoning should include regression warning
            assert "REGRESSION" in result.result.reasoning

    @pytest.mark.asyncio
    async def test_no_regression_keeps_original_result(self, node_analysis, tmp_path):
        """No regression keeps original confidence."""
        from wunderunner.agents.validation.regression import RegressionResult
        from wunderunner.models.context import ContextEntry, EntryType

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=9,
            reasoning="Good dockerfile",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        mock_regression = RegressionResult(
            has_regression=False,
            violations=[],
            adjusted_confidence=9,
        )
        mock_regression_result = MagicMock()
        mock_regression_result.output = mock_regression

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            fix="Previous fix",
            explanation="Details",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.regression_agent") as mock_reg_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            mock_reg_agent.USER_PROMPT.render.return_value = "regression prompt"
            mock_reg_agent.agent.run = AsyncMock(return_value=mock_regression_result)

            mock_load.return_value = mock_context

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            # Original confidence preserved
            assert result.result.confidence == 9
            assert "REGRESSION" not in result.result.reasoning
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_activity_dockerfile.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_activity_dockerfile.py
git commit -m "test: add integration tests for dockerfile generation activity"
```

---

## Task 5: Docker Build Activity Integration Test

**Files:**
- Create: `tests/test_activity_docker.py`

**Step 1: Write the tests for docker build activity**

```python
"""Integration tests for docker build activity."""

from unittest.mock import MagicMock, patch

import pytest
from docker.errors import ImageNotFound

from wunderunner.activities import docker
from wunderunner.exceptions import BuildError


class TestBuildActivity:
    """Integration tests for docker.build()."""

    @pytest.mark.asyncio
    async def test_fresh_build_creates_image(self, tmp_path):
        """Fresh build writes Dockerfile and builds image."""
        dockerfile_content = "FROM alpine:latest\nCMD echo hello"

        mock_image = MagicMock()
        mock_image.id = "sha256:abc123"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = [
            ImageNotFound("not found"),  # First call: cache miss
            mock_image,  # Second call: after build
        ]
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/2 : FROM alpine:latest\n"},
            {"stream": "Step 2/2 : CMD echo hello\n"},
        ])

        with patch("wunderunner.activities.docker.get_client", return_value=mock_client):
            result = await docker.build(tmp_path, dockerfile_content)

            # Dockerfile should be written
            assert (tmp_path / "Dockerfile").exists()
            assert (tmp_path / "Dockerfile").read_text() == dockerfile_content

            # Result should indicate no cache hit
            assert result.cache_hit is False
            assert result.image_id == "sha256:abc123"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_build(self, tmp_path):
        """Cache hit returns existing image without building."""
        dockerfile_content = "FROM alpine:latest\nCMD echo hello"

        mock_image = MagicMock()
        mock_image.id = "sha256:cached123"

        mock_client = MagicMock()
        mock_client.images.get.return_value = mock_image  # Cache hit

        with patch("wunderunner.activities.docker.get_client", return_value=mock_client):
            result = await docker.build(tmp_path, dockerfile_content)

            # Should NOT call build API
            mock_client.api.build.assert_not_called()

            # Result should indicate cache hit
            assert result.cache_hit is True
            assert result.image_id == "sha256:cached123"

    @pytest.mark.asyncio
    async def test_different_content_different_tag(self, tmp_path):
        """Different Dockerfile content produces different cache tags."""
        content1 = "FROM alpine:latest\nCMD echo hello"
        content2 = "FROM alpine:latest\nCMD echo world"

        tag1 = docker._compute_cache_tag(tmp_path, content1)
        tag2 = docker._compute_cache_tag(tmp_path, content2)

        assert tag1 != tag2
        assert tag1.startswith("wunderunner-")
        assert tag2.startswith("wunderunner-")

    @pytest.mark.asyncio
    async def test_different_path_different_tag(self, tmp_path):
        """Different project paths produce different cache tags."""
        content = "FROM alpine:latest\nCMD echo hello"

        path1 = tmp_path / "project1"
        path2 = tmp_path / "project2"
        path1.mkdir()
        path2.mkdir()

        tag1 = docker._compute_cache_tag(path1, content)
        tag2 = docker._compute_cache_tag(path2, content)

        assert tag1 != tag2

    @pytest.mark.asyncio
    async def test_build_error_raises_build_error(self, tmp_path):
        """Build failure raises BuildError with logs."""
        dockerfile_content = "FROM nonexistent:image"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/1 : FROM nonexistent:image\n"},
            {"error": "pull access denied for nonexistent"},
        ])

        with (
            patch("wunderunner.activities.docker.get_client", return_value=mock_client),
            pytest.raises(BuildError, match="Docker build failed"),
        ):
            await docker.build(tmp_path, dockerfile_content)

    @pytest.mark.asyncio
    async def test_build_completes_but_image_missing_raises(self, tmp_path):
        """Build completes without error but image not found raises BuildError."""
        dockerfile_content = "FROM alpine:latest"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")  # Always not found
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/1 : FROM alpine:latest\n"},
        ])

        with (
            patch("wunderunner.activities.docker.get_client", return_value=mock_client),
            pytest.raises(BuildError, match="image not created"),
        ):
            await docker.build(tmp_path, dockerfile_content)


class TestCacheTagGeneration:
    """Unit tests for cache tag generation."""

    def test_tag_format(self, tmp_path):
        """Tag follows expected format."""
        content = "FROM alpine"
        tag = docker._compute_cache_tag(tmp_path, content)

        assert tag.startswith("wunderunner-")
        parts = tag.split("-")
        assert len(parts) == 3
        # Each hash part should be 8 characters
        assert len(parts[1]) == 8
        assert len(parts[2]) == 8

    def test_tag_is_deterministic(self, tmp_path):
        """Same inputs produce same tag."""
        content = "FROM alpine"

        tag1 = docker._compute_cache_tag(tmp_path, content)
        tag2 = docker._compute_cache_tag(tmp_path, content)

        assert tag1 == tag2


class TestImageExists:
    """Unit tests for image existence check."""

    def test_image_exists_returns_true(self):
        """Returns True when image exists."""
        mock_client = MagicMock()
        mock_client.images.get.return_value = MagicMock()

        assert docker._image_exists(mock_client, "test:tag") is True

    def test_image_not_found_returns_false(self):
        """Returns False when image not found."""
        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")

        assert docker._image_exists(mock_client, "test:tag") is False
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_activity_docker.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_activity_docker.py
git commit -m "test: add integration tests for docker build activity"
```

---

## Task 6: Fixer/Improvement Activity Integration Test

**Files:**
- Create: `tests/test_activity_fixer.py`

**Step 1: Write tests for improvement activity**

```python
"""Integration tests for fixer/improvement activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import fixer
from wunderunner.models.generation import ImprovementResult
from wunderunner.workflows.state import Learning, Phase


class TestImproveDockerfile:
    """Integration tests for fixer.improve_dockerfile()."""

    @pytest.mark.asyncio
    async def test_improvement_returns_fixed_dockerfile(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Improvement returns fixed Dockerfile with confidence."""
        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\nRUN npm install\n",
            confidence=7,
            reasoning="Added missing npm install step",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            assert result.dockerfile == "FROM node:20-slim\nRUN npm install\n"
            assert result.confidence == 7
            assert "npm install" in result.reasoning

    @pytest.mark.asyncio
    async def test_improvement_can_modify_project_files(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Improvement agent can modify project files."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=8,
            reasoning="Removed conflicting .babelrc",
            files_modified=[".babelrc"],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            assert ".babelrc" in result.files_modified

    @pytest.mark.asyncio
    async def test_agent_error_returns_unchanged_dockerfile(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Agent failure returns original Dockerfile with zero confidence."""
        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API error"))
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            # Should return unchanged Dockerfile
            assert result.dockerfile == valid_dockerfile
            assert result.confidence == 0
            assert "error" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_attempt_number_passed_to_prompt(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Attempt number is passed to agent for context."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=5,
            reasoning="Attempt 3 fix",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=3,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("attempt_number") == 3

    @pytest.mark.asyncio
    async def test_timeout_error_sets_exit_code_124(
        self, node_analysis, valid_dockerfile, tmp_path
    ):
        """Timeout errors set exit_code to 124."""
        timeout_learning = Learning(
            phase=Phase.HEALTHCHECK,
            error_type="HealthcheckError",
            error_message="Container timed out waiting for health",
        )
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=6,
            reasoning="Fixed timeout issue",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=timeout_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("exit_code") == 124

    @pytest.mark.asyncio
    async def test_historical_fixes_passed_for_antiregression(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Historical fixes are passed to agent for anti-regression."""
        from wunderunner.models.context import ContextEntry, EntryType

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            error="Previous build error",
            fix="Added npm ci",
            explanation="npm ci is faster than npm install",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]

        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=7,
            reasoning="Applied fix",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = mock_context

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("historical_fixes") == [historical_fix]

    @pytest.mark.asyncio
    async def test_improvement_recorded_to_context(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Successful improvement is recorded to context storage."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=8,
            reasoning="Fixed the issue",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock) as mock_add,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            # Verify entry was added to context
            mock_add.assert_called_once()
            call_args = mock_add.call_args
            assert call_args[0][0] == tmp_path  # project_path
            entry = call_args[0][1]
            assert "confidence 8" in entry.fix
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_activity_fixer.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_activity_fixer.py
git commit -m "test: add integration tests for fixer/improvement activity"
```

---

## Task 7: Service Detection Activity Integration Test

**Files:**
- Modify: `tests/test_activities_service_detection.py`

**Step 1: Replace placeholder tests with real integration tests**

```python
"""Integration tests for service detection activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import service_detection
from wunderunner.models.analysis import DetectedService, EnvVar, ServiceConfig


class TestDetectServices:
    """Integration tests for service_detection.detect_services()."""

    @pytest.mark.asyncio
    async def test_empty_env_vars_returns_empty_list(self):
        """No env vars returns empty list without calling agent."""
        with patch("wunderunner.activities.service_detection.services_agent") as mock_agent:
            result = await service_detection.detect_services([])

            assert result == []
            mock_agent.agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_detects_postgres_from_database_url(self):
        """Detects postgres service from DATABASE_URL env var."""
        env_vars = [
            EnvVar(name="DATABASE_URL", required=True),
            EnvVar(name="PORT", required=False, default="3000"),
        ]

        mock_detected = [
            DetectedService(
                type="postgres",
                env_vars=["DATABASE_URL"],
                confidence=0.9,
            )
        ]
        mock_result = MagicMock()
        mock_result.output = mock_detected

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await service_detection.detect_services(env_vars)

            assert len(result) == 1
            assert result[0].type == "postgres"
            assert "DATABASE_URL" in result[0].env_vars

    @pytest.mark.asyncio
    async def test_detects_multiple_services(self):
        """Detects multiple services from env vars."""
        env_vars = [
            EnvVar(name="DATABASE_URL", required=True),
            EnvVar(name="REDIS_URL", required=True),
        ]

        mock_detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]
        mock_result = MagicMock()
        mock_result.output = mock_detected

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            result = await service_detection.detect_services(env_vars)

            assert len(result) == 2
            types = [s.type for s in result]
            assert "postgres" in types
            assert "redis" in types

    @pytest.mark.asyncio
    async def test_agent_error_returns_empty_list(self):
        """Agent failure returns empty list gracefully."""
        env_vars = [EnvVar(name="DATABASE_URL", required=True)]

        with (
            patch("wunderunner.activities.service_detection.services_agent") as mock_agent,
            patch("wunderunner.activities.service_detection.get_fallback_model"),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API error"))

            result = await service_detection.detect_services(env_vars)

            # Should return empty list, not raise
            assert result == []


class TestConfirmServices:
    """Tests for service_detection.confirm_services()."""

    def test_all_confirmed_returns_all(self):
        """All confirmed services are returned as ServiceConfig."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]

        def always_confirm(service_type: str, env_vars: list[str]) -> bool:
            return True

        result = service_detection.confirm_services(detected, always_confirm)

        assert len(result) == 2
        assert all(isinstance(s, ServiceConfig) for s in result)
        types = [s.type for s in result]
        assert "postgres" in types
        assert "redis" in types

    def test_none_confirmed_returns_empty(self):
        """No confirmed services returns empty list."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
        ]

        def never_confirm(service_type: str, env_vars: list[str]) -> bool:
            return False

        result = service_detection.confirm_services(detected, never_confirm)

        assert result == []

    def test_partial_confirmation(self):
        """Only confirmed services are returned."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
            DetectedService(type="redis", env_vars=["REDIS_URL"], confidence=0.85),
        ]

        def confirm_postgres_only(service_type: str, env_vars: list[str]) -> bool:
            return service_type == "postgres"

        result = service_detection.confirm_services(detected, confirm_postgres_only)

        assert len(result) == 1
        assert result[0].type == "postgres"

    def test_env_vars_preserved_in_service_config(self):
        """Env vars are preserved in ServiceConfig."""
        detected = [
            DetectedService(
                type="postgres",
                env_vars=["DATABASE_URL", "DB_HOST", "DB_PORT"],
                confidence=0.9,
            ),
        ]

        def always_confirm(service_type: str, env_vars: list[str]) -> bool:
            return True

        result = service_detection.confirm_services(detected, always_confirm)

        assert result[0].env_vars == ["DATABASE_URL", "DB_HOST", "DB_PORT"]

    def test_callback_receives_correct_args(self):
        """Callback receives service type and env vars."""
        detected = [
            DetectedService(type="postgres", env_vars=["DATABASE_URL"], confidence=0.9),
        ]

        received_calls = []

        def tracking_callback(service_type: str, env_vars: list[str]) -> bool:
            received_calls.append((service_type, env_vars))
            return True

        service_detection.confirm_services(detected, tracking_callback)

        assert len(received_calls) == 1
        assert received_calls[0] == ("postgres", ["DATABASE_URL"])
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_activities_service_detection.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_activities_service_detection.py
git commit -m "test: add integration tests for service detection activity"
```

---

## Task 8: Workflow Node Integration Tests

**Files:**
- Create: `tests/test_workflow_nodes.py`

**Step 1: Write tests for individual workflow nodes**

```python
"""Integration tests for workflow nodes."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import GraphRunContext

from wunderunner.workflows.containerize import (
    Analyze,
    Build,
    CollectSecrets,
    Dockerfile,
    Healthcheck,
    HumanHint,
    ImproveDockerfile,
    RetryOrHint,
    Services,
    Start,
    Validate,
)
from wunderunner.workflows.state import ContainerizeState, Learning, Phase, Severity


@pytest.fixture
def mock_ctx(workflow_state):
    """Create a mock GraphRunContext."""
    ctx = MagicMock(spec=GraphRunContext)
    ctx.state = workflow_state
    return ctx


class TestAnalyzeNode:
    """Tests for Analyze workflow node."""

    @pytest.mark.asyncio
    async def test_analyze_sets_analysis_on_state(self, mock_ctx, node_analysis):
        """Analyze node sets analysis result on state."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = node_analysis

            node = Analyze()
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.analysis == node_analysis
            # Should return Dockerfile node (no secrets)
            assert isinstance(next_node, Dockerfile)

    @pytest.mark.asyncio
    async def test_analyze_with_secrets_returns_collect_secrets(
        self, mock_ctx, analysis_with_secrets
    ):
        """Analyze with secrets returns CollectSecrets node."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = analysis_with_secrets

            node = Analyze()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, CollectSecrets)

    @pytest.mark.asyncio
    async def test_analyze_reports_progress(self, mock_ctx, node_analysis, progress_messages):
        """Analyze node reports progress via callback."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = node_analysis

            node = Analyze()
            await node.run(mock_ctx)

            # Should have progress messages
            assert len(progress_messages) >= 2
            severities = [s for s, _ in progress_messages]
            assert Severity.INFO in severities
            assert Severity.SUCCESS in severities


class TestCollectSecretsNode:
    """Tests for CollectSecrets workflow node."""

    @pytest.mark.asyncio
    async def test_collects_secrets_via_callback(self, mock_ctx, analysis_with_secrets):
        """CollectSecrets prompts for each secret via callback."""
        mock_ctx.state.analysis = analysis_with_secrets

        secret_prompts = []
        def mock_secret_prompt(name: str, service: str | None) -> str:
            secret_prompts.append((name, service))
            return f"value_for_{name}"

        mock_ctx.state.on_secret_prompt = mock_secret_prompt

        node = CollectSecrets()
        next_node = await node.run(mock_ctx)

        # Should have prompted for each secret
        assert len(secret_prompts) == 2  # DATABASE_URL, API_KEY
        secret_names = [name for name, _ in secret_prompts]
        assert "DATABASE_URL" in secret_names
        assert "API_KEY" in secret_names

        # Values should be stored
        assert mock_ctx.state.secret_values["DATABASE_URL"] == "value_for_DATABASE_URL"
        assert mock_ctx.state.secret_values["API_KEY"] == "value_for_API_KEY"

        # Should return Dockerfile node
        assert isinstance(next_node, Dockerfile)


class TestDockerfileNode:
    """Tests for Dockerfile workflow node."""

    @pytest.mark.asyncio
    async def test_generates_dockerfile_on_state(self, mock_ctx, node_analysis):
        """Dockerfile node generates and stores content."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        mock_ctx.state.analysis = node_analysis
        mock_result = GenerateResult(
            result=DockerfileResult(
                dockerfile="FROM node:20-slim\n",
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_result

            node = Dockerfile()
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.dockerfile_content == "FROM node:20-slim\n"
            assert mock_ctx.state.last_confidence == 8
            assert isinstance(next_node, Validate)

    @pytest.mark.asyncio
    async def test_dockerfile_error_returns_retry_or_hint(self, mock_ctx, node_analysis):
        """Dockerfile generation error returns RetryOrHint."""
        from wunderunner.exceptions import DockerfileError

        mock_ctx.state.analysis = node_analysis

        with patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = DockerfileError("Generation failed")

            node = Dockerfile()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, RetryOrHint)
            assert len(mock_ctx.state.learnings) == 1
            assert mock_ctx.state.learnings[0].phase == Phase.DOCKERFILE


class TestValidateNode:
    """Tests for Validate workflow node."""

    @pytest.mark.asyncio
    async def test_valid_returns_services(self, mock_ctx, node_analysis, passing_validation):
        """Valid Dockerfile returns Services node."""
        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"

        with patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = passing_validation

            node = Validate()
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.last_validation_grade == 85
            assert isinstance(next_node, Services)

    @pytest.mark.asyncio
    async def test_invalid_returns_retry_or_hint(self, mock_ctx, node_analysis, failing_validation):
        """Invalid Dockerfile returns RetryOrHint."""
        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"

        with patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = failing_validation

            node = Validate()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, RetryOrHint)
            assert mock_ctx.state.last_validation_grade == 45


class TestRetryOrHintNode:
    """Tests for RetryOrHint decision node."""

    @pytest.mark.asyncio
    async def test_runtime_error_returns_improve_dockerfile(self, mock_ctx, build_learning):
        """Runtime phase error (build/start/healthcheck) returns ImproveDockerfile."""
        mock_ctx.state.retry_count = 0

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, ImproveDockerfile)
            assert mock_ctx.state.retry_count == 1

    @pytest.mark.asyncio
    async def test_validation_error_returns_dockerfile(self, mock_ctx, validation_learning):
        """Validation phase error returns Dockerfile for regeneration."""
        mock_ctx.state.retry_count = 0

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=validation_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, Dockerfile)
            assert mock_ctx.state.retry_count == 1

    @pytest.mark.asyncio
    async def test_max_attempts_returns_human_hint(self, mock_ctx, build_learning):
        """Exceeding max attempts returns HumanHint."""
        mock_ctx.state.retry_count = 2

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, HumanHint)


class TestHumanHintNode:
    """Tests for HumanHint workflow node."""

    @pytest.mark.asyncio
    async def test_hint_provided_returns_dockerfile(self, mock_ctx):
        """User hint resets retry count and returns Dockerfile."""
        mock_ctx.state.retry_count = 3
        mock_ctx.state.learnings = [
            Learning(phase=Phase.BUILD, error_type="BuildError", error_message="Failed")
        ]
        mock_ctx.state.on_hint_prompt = lambda learnings: "Try using alpine base"

        node = HumanHint()
        next_node = await node.run(mock_ctx)

        assert isinstance(next_node, Dockerfile)
        assert mock_ctx.state.retry_count == 0
        assert "Try using alpine base" in mock_ctx.state.hints

    @pytest.mark.asyncio
    async def test_no_hint_raises_keyboard_interrupt(self, mock_ctx):
        """No hint (None) raises KeyboardInterrupt to quit."""
        mock_ctx.state.learnings = []
        mock_ctx.state.on_hint_prompt = lambda learnings: None

        node = HumanHint()

        with pytest.raises(KeyboardInterrupt):
            await node.run(mock_ctx)


class TestImproveDockerfileNode:
    """Tests for ImproveDockerfile workflow node."""

    @pytest.mark.asyncio
    async def test_improvement_updates_state(self, mock_ctx, node_analysis, build_learning):
        """Improvement updates Dockerfile content and confidence."""
        from wunderunner.models.generation import ImprovementResult

        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:18-slim\n"
        mock_ctx.state.retry_count = 1

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\n",
            confidence=7,
            reasoning="Upgraded Node version",
            files_modified=[],
        )

        with (
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fix,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
        ):
            mock_fix.return_value = mock_improvement
            mock_settings.return_value.max_attempts = 3

            node = ImproveDockerfile(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.dockerfile_content == "FROM node:20-slim\n"
            assert mock_ctx.state.last_confidence == 7
            assert isinstance(next_node, Validate)

    @pytest.mark.asyncio
    async def test_compose_modification_skips_services_regen(
        self, mock_ctx, node_analysis, build_learning
    ):
        """Compose file modification sets skip_services_regen flag."""
        from wunderunner.models.generation import ImprovementResult

        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"
        mock_ctx.state.retry_count = 1

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\n",
            confidence=8,
            reasoning="Fixed compose",
            files_modified=["docker-compose.yaml"],
        )

        with (
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fix,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
        ):
            mock_fix.return_value = mock_improvement
            mock_settings.return_value.max_attempts = 3

            node = ImproveDockerfile(learning=build_learning)
            next_node = await node.run(mock_ctx)

            # Should skip to Build instead of Validate
            assert isinstance(next_node, Build)
            # Flag should be reset after use
            assert mock_ctx.state.skip_services_regen is False
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_nodes.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_workflow_nodes.py
git commit -m "test: add integration tests for workflow nodes"
```

---

## Task 9: Workflow End-to-End Happy Path Test

**Files:**
- Create: `tests/test_workflow_e2e.py`

**Step 1: Write end-to-end workflow test**

```python
"""End-to-end integration tests for containerize workflow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.workflows.containerize import Success, containerize_graph
from wunderunner.workflows.state import ContainerizeState, Severity


class TestWorkflowHappyPath:
    """End-to-end tests for successful workflow execution."""

    @pytest.mark.asyncio
    async def test_full_workflow_success(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Full workflow completes successfully with all mocked activities."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        progress_messages = []

        def track_progress(severity: Severity, message: str) -> None:
            progress_messages.append((severity, message))

        state = ContainerizeState(
            path=tmp_path,
            on_progress=track_progress,
        )

        # Mock all activities
        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with (
            # Analysis
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            # Dockerfile generation
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            # Validation
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            # Services generation
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            # Docker build
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            # Start containers
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            # Healthcheck
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            # File write
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose

            from wunderunner.activities.docker import BuildResult
            mock_build.return_value = BuildResult(image_id="sha256:abc", cache_hit=False)
            mock_start.return_value = ["container1"]
            mock_health.return_value = None  # Success

            # Mock aiofiles context manager
            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            # Run workflow
            result = await containerize_graph.run(state)

            # Verify success
            assert isinstance(result.output, Success)

            # Verify all activities were called
            mock_analyze.assert_called_once()
            mock_dockerfile.assert_called_once()
            mock_validate.assert_called_once()
            mock_services.assert_called_once()
            mock_build.assert_called_once()
            mock_start.assert_called_once()
            mock_health.assert_called_once()

            # Verify progress messages include success indicators
            severities = [s for s, _ in progress_messages]
            assert Severity.SUCCESS in severities

    @pytest.mark.asyncio
    async def test_workflow_with_secrets_collects_them(
        self,
        tmp_path,
        analysis_with_secrets,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Workflow with secrets prompts for and collects them."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        collected_secrets = {}

        def secret_prompt(name: str, service: str | None) -> str:
            value = f"secret_value_for_{name}"
            collected_secrets[name] = value
            return value

        state = ContainerizeState(
            path=tmp_path,
            on_secret_prompt=secret_prompt,
        )

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = analysis_with_secrets
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose

            from wunderunner.activities.docker import BuildResult
            mock_build.return_value = BuildResult(image_id="sha256:abc", cache_hit=False)
            mock_start.return_value = ["container1"]
            mock_health.return_value = None

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(state)

            assert isinstance(result.output, Success)

            # Verify secrets were collected
            assert "DATABASE_URL" in collected_secrets
            assert "API_KEY" in collected_secrets

            # Verify secrets are stored on state
            assert state.secret_values["DATABASE_URL"] == "secret_value_for_DATABASE_URL"


class TestWorkflowErrorRecovery:
    """Tests for workflow error recovery paths."""

    @pytest.mark.asyncio
    async def test_build_error_triggers_improvement(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Build error triggers improvement agent and retry."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.activities.docker import BuildResult
        from wunderunner.exceptions import BuildError
        from wunderunner.models.generation import DockerfileResult, ImprovementResult

        state = ContainerizeState(path=tmp_path)

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\nRUN npm install\n",
            confidence=7,
            reasoning="Fixed build",
            files_modified=[],
        )

        build_call_count = 0

        async def mock_build_with_failure(*args, **kwargs):
            nonlocal build_call_count
            build_call_count += 1
            if build_call_count == 1:
                raise BuildError("npm install failed")
            return BuildResult(image_id="sha256:abc", cache_hit=False)

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fixer,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose
            mock_build.side_effect = mock_build_with_failure
            mock_fixer.return_value = mock_improvement
            mock_start.return_value = ["container1"]
            mock_health.return_value = None
            mock_settings.return_value.max_attempts = 3

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(state)

            # Should eventually succeed
            assert isinstance(result.output, Success)

            # Fixer should have been called
            mock_fixer.assert_called_once()

            # Build should have been called twice
            assert build_call_count == 2

            # Learnings should include build error
            assert len(state.learnings) >= 1
            assert any(l.phase.value == "build" for l in state.learnings)

    @pytest.mark.asyncio
    async def test_max_retries_triggers_human_hint(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Exceeding max retries asks for human hint."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.activities.docker import BuildResult
        from wunderunner.exceptions import BuildError
        from wunderunner.models.generation import DockerfileResult, ImprovementResult

        hint_requested = []

        def hint_prompt(learnings):
            hint_requested.append(learnings)
            return "Use node:20-alpine instead"

        state = ContainerizeState(
            path=tmp_path,
            on_hint_prompt=hint_prompt,
        )

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,  # Still fails
            confidence=3,
            reasoning="Not sure",
            files_modified=[],
        )

        build_call_count = 0

        async def mock_build_with_failures(*args, **kwargs):
            nonlocal build_call_count
            build_call_count += 1
            if build_call_count <= 3:
                raise BuildError(f"Build failed attempt {build_call_count}")
            return BuildResult(image_id="sha256:abc", cache_hit=False)

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fixer,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose
            mock_build.side_effect = mock_build_with_failures
            mock_fixer.return_value = mock_improvement
            mock_start.return_value = ["container1"]
            mock_health.return_value = None
            mock_settings.return_value.max_attempts = 3

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(state)

            # Should eventually succeed after human hint
            assert isinstance(result.output, Success)

            # Human hint should have been requested
            assert len(hint_requested) >= 1

            # Hint should be stored in state
            assert "Use node:20-alpine instead" in state.hints
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_e2e.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_workflow_e2e.py
git commit -m "test: add end-to-end integration tests for workflow"
```

---

## Task 10: Run Full Test Suite and Verify Coverage

**Files:** None (verification only)

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Check test count increased significantly**

Run: `uv run pytest tests/ --collect-only | grep "test session starts" -A 5`
Expected: Test count should be 100+ (up from ~55)

**Step 3: Run with coverage (optional)**

Run: `uv run pytest tests/ --cov=wunderunner --cov-report=term-missing`
Expected: Coverage report showing tested modules

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: complete integration test suite for activities and workflow"
```

---

## Summary

This plan adds **9 new test files** with comprehensive integration tests:

1. **conftest.py** - Shared fixtures for all tests
2. **test_workflow_state.py** - Enhanced state mutation tests
3. **test_activity_validation.py** - Two-tier validation tests
4. **test_activity_dockerfile.py** - Dockerfile generation with regression
5. **test_activity_docker.py** - Docker build with caching
6. **test_activity_fixer.py** - Improvement/fixer activity
7. **test_activities_service_detection.py** - Service detection activity
8. **test_workflow_nodes.py** - Individual workflow node tests
9. **test_workflow_e2e.py** - End-to-end workflow tests

**Total new tests:** ~80+ test functions
**Test patterns used:**
- AsyncMock for async activities
- MagicMock for agent responses
- patch for dependency injection
- pytest fixtures for test data
- tmp_path for file I/O tests

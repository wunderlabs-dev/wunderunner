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

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

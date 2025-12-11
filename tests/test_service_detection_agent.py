"""Tests for service detection agent."""

from wunderunner.models.analysis import DetectedService


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

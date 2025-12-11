"""Service detection activity."""

import logging

from wunderunner.agents.analysis import services as services_agent
from wunderunner.models.analysis import DetectedService, EnvVar, ServiceConfig
from wunderunner.settings import Analysis as AnalysisAgent
from wunderunner.settings import get_fallback_model
from wunderunner.workflows.state import ServicePromptCallback

logger = logging.getLogger(__name__)


async def detect_services(env_vars: list[EnvVar]) -> list[DetectedService]:
    """Detect external services from environment variables.

    Args:
        env_vars: Combined list of env vars and secrets from analysis.

    Returns:
        List of detected services with their associated env vars.
    """
    if not env_vars:
        return []

    prompt = services_agent.USER_PROMPT.render(env_vars=env_vars)

    try:
        result = await services_agent.agent.run(
            prompt,
            model=get_fallback_model(AnalysisAgent.ENV_VARS),
        )
        return result.output
    except Exception as e:
        logger.warning("Service detection failed: %s", e)
        return []


def confirm_services(
    detected: list[DetectedService],
    prompt_callback: ServicePromptCallback,
) -> list[ServiceConfig]:
    """Prompt user to confirm which detected services to create.

    Args:
        detected: Services detected by the agent.
        prompt_callback: Callback to prompt user (service_type, env_vars) -> bool.

    Returns:
        List of confirmed ServiceConfig objects.
    """
    confirmed = []
    for service in detected:
        if prompt_callback(service.type, service.env_vars):
            confirmed.append(
                ServiceConfig(type=service.type, env_vars=service.env_vars)
            )
    return confirmed

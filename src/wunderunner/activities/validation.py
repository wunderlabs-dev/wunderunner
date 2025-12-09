"""Dockerfile validation activity with two-tier validation."""

from wunderunner.agents.validation import dockerfile as dockerfile_agent
from wunderunner.exceptions import ValidationError
from wunderunner.models.analysis import Analysis
from wunderunner.models.validation import ValidationResult
from wunderunner.validation.dockerfile import validate_dockerfile_syntax
from wunderunner.workflows.state import Learning

# Minimum grade to pass validation
PASSING_GRADE = 80


def _format_learnings(learnings: list[Learning]) -> str:
    """Format learnings for the validation prompt."""
    if not learnings:
        return "None"

    lines = []
    for learning in learnings:
        lines.append(f"- [{learning.phase}] {learning.error_type}: {learning.error_message}")
        if learning.context:
            lines.append(f"  Context: {learning.context}")
    return "\n".join(lines)


def _build_prompt(
    dockerfile: str,
    analysis: Analysis,
    learnings: list[Learning],
) -> str:
    """Build the validation prompt."""
    parts = []

    parts.append("<dockerfile>")
    parts.append(dockerfile)
    parts.append("</dockerfile>")

    parts.append("\n<project_context>")
    parts.append(f"Runtime: {analysis.project_structure.runtime}")
    if analysis.project_structure.runtime_version:
        parts.append(f"Runtime Version: {analysis.project_structure.runtime_version}")
    if analysis.project_structure.framework:
        parts.append(f"Framework: {analysis.project_structure.framework}")
    parts.append(f"Package Manager: {analysis.project_structure.package_manager}")
    parts.append("</project_context>")

    # Required secrets for grading
    secrets = [v.name for v in analysis.env_vars if v.secret]
    if secrets:
        parts.append("\n<required_secrets>")
        for secret in secrets:
            parts.append(f"- {secret}")
        parts.append("</required_secrets>")
    else:
        parts.append("\n<required_secrets>None</required_secrets>")

    # Previous errors to consider for bonus points
    if learnings:
        parts.append("\n<previous_errors>")
        parts.append(_format_learnings(learnings))
        parts.append("</previous_errors>")

    parts.append("\nGrade this Dockerfile using the rubric in your system prompt.")

    return "\n".join(parts)


async def validate(
    dockerfile: str,
    analysis: Analysis,
    learnings: list[Learning] | None = None,
) -> ValidationResult:
    """Validate a Dockerfile using two-tier validation.

    First runs programmatic checks (fast, deterministic).
    If those pass, runs LLM-based grading.

    Args:
        dockerfile: The Dockerfile content to validate.
        analysis: Project analysis for context.
        learnings: Previous errors to consider for bonus points.

    Returns:
        ValidationResult with grade and feedback.

    Raises:
        ValidationError: If validation fails unexpectedly.
    """
    learnings = learnings or []

    # Tier 1: Programmatic validation
    required_secrets = [v.name for v in analysis.env_vars if v.secret]
    issues = validate_dockerfile_syntax(dockerfile, required_secrets)

    if issues:
        # Fast fail - skip LLM grading
        return ValidationResult.programmatic_failure(issues)

    # Tier 2: LLM-based grading
    prompt = _build_prompt(dockerfile, analysis, learnings)

    try:
        result = await dockerfile_agent.agent.run(prompt)
        validation = result.output

        # Ensure is_valid matches grade threshold
        validation.is_valid = validation.grade >= PASSING_GRADE

        # If invalid, populate issues from recommendations
        if not validation.is_valid and not validation.issues:
            validation.issues = validation.recommendations

        return validation
    except Exception as e:
        raise ValidationError(f"Failed to validate Dockerfile: {e}") from e

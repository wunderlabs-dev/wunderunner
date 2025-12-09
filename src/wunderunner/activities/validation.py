"""Dockerfile validation activity with two-tier validation."""

from wunderunner.agents.validation import dockerfile as dockerfile_agent
from wunderunner.exceptions import ValidationError
from wunderunner.models.analysis import Analysis
from wunderunner.models.validation import ValidationResult
from wunderunner.validation.dockerfile import validate_dockerfile_syntax
from wunderunner.workflows.state import Learning

# Minimum grade to pass validation
PASSING_GRADE = 80


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
    prompt = dockerfile_agent.USER_PROMPT.render(
        dockerfile=dockerfile,
        analysis=analysis.model_dump(),
        learnings=learnings,
    )

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

"""Parse plan.md artifact to extract file contents and verification steps."""

import re
from dataclasses import dataclass


@dataclass
class VerificationStep:
    """A verification step extracted from plan."""

    command: str
    expected: str


@dataclass
class ParsedPlan:
    """Parsed contents of plan.md."""

    dockerfile: str | None
    compose: str | None
    verification_steps: list[VerificationStep]


def parse_plan(plan_content: str) -> ParsedPlan:
    """Parse plan.md content to extract file contents.

    Extracts:
    - Dockerfile content from ```dockerfile code block
    - docker-compose.yaml content from ```yaml code block
    - Verification steps from numbered list

    Args:
        plan_content: Raw markdown content of plan.md.

    Returns:
        ParsedPlan with extracted contents.
    """
    dockerfile = _extract_code_block(plan_content, "dockerfile")
    compose = _extract_code_block(plan_content, "yaml")
    verification = _extract_verification_steps(plan_content)

    return ParsedPlan(
        dockerfile=dockerfile,
        compose=compose,
        verification_steps=verification,
    )


def _extract_code_block(content: str, language: str) -> str | None:
    """Extract content from a fenced code block.

    Args:
        content: Markdown content.
        language: Code block language (dockerfile, yaml).

    Returns:
        Code block content without fences, or None if not found.
    """
    # Match ```language ... ``` blocks
    pattern = rf"```{language}\n(.*?)```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def _extract_verification_steps(content: str) -> list[VerificationStep]:
    """Extract verification steps from numbered list.

    Expected format:
    1. `command` → expected
    2. `command` → expected

    Args:
        content: Markdown content.

    Returns:
        List of VerificationStep objects.
    """
    steps: list[VerificationStep] = []

    # Find the Verification section
    verification_match = re.search(r"## Verification\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if not verification_match:
        return steps

    verification_section = verification_match.group(1)

    # Match numbered items: 1. `command` → expected
    pattern = r"\d+\.\s+`([^`]+)`\s+→\s+(.+)"
    for match in re.finditer(pattern, verification_section):
        command = match.group(1).strip()
        expected = match.group(2).strip()
        steps.append(VerificationStep(command=command, expected=expected))

    return steps

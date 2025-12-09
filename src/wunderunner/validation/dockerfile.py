"""Programmatic validation for Dockerfiles.

These checks are fast and deterministic, run before LLM grading.
Only reject on critical structural issues that would definitely fail.
"""

import re


def validate_dockerfile_syntax(content: str, required_secrets: list[str]) -> list[str]:
    """Validate Dockerfile syntax and structure.

    Returns list of issues. Empty list means valid.

    Args:
        content: Dockerfile content as string.
        required_secrets: List of secret names that must have ARG + ENV declarations.

    Returns:
        List of validation issues. Empty if valid.
    """
    issues: list[str] = []

    if not content or not content.strip():
        return ["Dockerfile is empty"]

    lines = content.strip().split("\n")

    # Check for unfilled template placeholders
    placeholder_pattern = re.compile(r"\{\{.*?\}\}")
    for i, line in enumerate(lines, 1):
        if placeholder_pattern.search(line):
            issues.append(f"Line {i}: Unfilled template placeholder found")

    # Find first non-comment, non-empty instruction
    first_instruction = _find_first_instruction(lines)
    if first_instruction is None:
        issues.append("No instructions found in Dockerfile")
        return issues

    # FROM must be first instruction (ARG for base image is allowed before FROM)
    if not _is_valid_first_instruction(first_instruction):
        issues.append(
            f"First instruction must be FROM or ARG (for base image), got: {first_instruction}"
        )

    # Check for WORKDIR instruction
    if not _has_instruction(lines, "WORKDIR"):
        issues.append("Missing WORKDIR instruction")

    # Check for required secrets (ARG + ENV pairs)
    for secret in required_secrets:
        secret_issues = _validate_secret_declaration(lines, secret)
        issues.extend(secret_issues)

    return issues


def _find_first_instruction(lines: list[str]) -> str | None:
    """Find the first non-comment, non-empty line."""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _is_valid_first_instruction(instruction: str) -> bool:
    """Check if first instruction is valid (FROM or ARG for base image)."""
    upper = instruction.upper()
    return upper.startswith("FROM ") or upper.startswith("ARG ")


def _has_instruction(lines: list[str], instruction: str) -> bool:
    """Check if Dockerfile contains a specific instruction."""
    pattern = re.compile(rf"^\s*{instruction}\s+", re.IGNORECASE)
    return any(pattern.match(line) for line in lines)


def _validate_secret_declaration(lines: list[str], secret_name: str) -> list[str]:
    """Validate that a secret has proper ARG and ENV declarations.

    Expected format:
    ARG SECRET_NAME
    ENV SECRET_NAME=$SECRET_NAME

    Returns list of issues for this specific secret.
    """
    issues = []

    # Check for ARG declaration
    arg_pattern = re.compile(rf"^\s*ARG\s+{re.escape(secret_name)}\s*$", re.IGNORECASE)
    has_arg = any(arg_pattern.match(line) for line in lines)

    # Check for ENV declaration (multiple valid formats)
    # ENV SECRET=$SECRET or ENV SECRET=${SECRET} or ENV SECRET=$SECRET_NAME
    env_pattern = re.compile(
        rf"^\s*ENV\s+{re.escape(secret_name)}\s*=\s*\$\{{?{re.escape(secret_name)}\}}?\s*$",
        re.IGNORECASE,
    )
    has_env = any(env_pattern.match(line) for line in lines)

    if not has_arg:
        issues.append(f"Missing ARG declaration for secret: {secret_name}")
    if not has_env:
        issues.append(f"Missing ENV declaration for secret: {secret_name}")

    return issues

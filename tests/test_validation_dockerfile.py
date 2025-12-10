"""Tests for Dockerfile programmatic validation."""

from wunderunner.validation.dockerfile import validate_dockerfile_syntax


class TestValidateDockerfileSyntax:
    """Tests for validate_dockerfile_syntax function."""

    def test_empty_dockerfile(self) -> None:
        """Empty dockerfile should fail."""
        issues = validate_dockerfile_syntax("", [])
        assert "Dockerfile is empty" in issues

    def test_whitespace_only_dockerfile(self) -> None:
        """Whitespace-only dockerfile should fail."""
        issues = validate_dockerfile_syntax("   \n\n   ", [])
        assert "Dockerfile is empty" in issues

    def test_comments_only_dockerfile(self) -> None:
        """Comments-only dockerfile should fail."""
        issues = validate_dockerfile_syntax("# This is a comment\n# Another comment", [])
        assert "No instructions found in Dockerfile" in issues

    def test_valid_simple_dockerfile(self) -> None:
        """Valid simple dockerfile should pass."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm install
CMD ["npm", "start"]
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert issues == []

    def test_missing_from_instruction(self) -> None:
        """Dockerfile without FROM as first instruction should fail."""
        dockerfile = """WORKDIR /app
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert any("First instruction must be FROM" in issue for issue in issues)

    def test_arg_before_from_is_valid(self) -> None:
        """ARG before FROM is valid (for base image variables)."""
        dockerfile = """ARG NODE_VERSION=20
FROM node:${NODE_VERSION}-alpine
WORKDIR /app
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert issues == []

    def test_missing_workdir(self) -> None:
        """Dockerfile without WORKDIR should fail."""
        dockerfile = """FROM node:20-alpine
COPY . .
RUN npm install
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert "Missing WORKDIR instruction" in issues

    def test_unfilled_template_placeholder(self) -> None:
        """Dockerfile with template placeholders should fail."""
        dockerfile = """FROM node:{{nodeVersion}}-alpine
WORKDIR /app
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert any("Unfilled template placeholder" in issue for issue in issues)

    def test_secret_missing_arg(self) -> None:
        """Missing ARG for secret should fail."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
ENV DATABASE_URL=$DATABASE_URL
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL"])
        assert "Missing ARG declaration for secret: DATABASE_URL" in issues

    def test_secret_missing_env(self) -> None:
        """Missing ENV for secret should fail."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
ARG DATABASE_URL
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL"])
        assert "Missing ENV declaration for secret: DATABASE_URL" in issues

    def test_secret_properly_declared(self) -> None:
        """Properly declared secret should pass."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
ARG DATABASE_URL
ENV DATABASE_URL=$DATABASE_URL
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL"])
        assert issues == []

    def test_secret_with_braces(self) -> None:
        """Secret with ${} syntax should pass."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL"])
        assert issues == []

    def test_multiple_secrets(self) -> None:
        """Multiple secrets should all be validated."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
ARG DATABASE_URL
ENV DATABASE_URL=$DATABASE_URL
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL", "API_KEY"])
        assert "Missing ARG declaration for secret: API_KEY" in issues
        assert "Missing ENV declaration for secret: API_KEY" in issues

    def test_case_insensitive_instructions(self) -> None:
        """Dockerfile instructions should be case-insensitive."""
        dockerfile = """from node:20-alpine
workdir /app
arg DATABASE_URL
env DATABASE_URL=$DATABASE_URL
copy . .
"""
        issues = validate_dockerfile_syntax(dockerfile, ["DATABASE_URL"])
        assert issues == []

    def test_no_required_secrets(self) -> None:
        """Dockerfile without required secrets should pass secret validation."""
        dockerfile = """FROM node:20-alpine
WORKDIR /app
COPY . .
"""
        issues = validate_dockerfile_syntax(dockerfile, [])
        assert issues == []

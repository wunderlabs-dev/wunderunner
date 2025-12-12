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

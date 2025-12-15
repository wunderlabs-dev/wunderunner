"""Tests for regression detection agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jinja2 import Template

from wunderunner.agents.validation.regression import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    RegressionResult,
    agent,
)


class TestRegressionPrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined and non-empty."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 50

    def test_user_prompt_is_template(self):
        """User prompt is a Jinja2 template."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, Template)

    def test_system_prompt_mentions_regression(self):
        """System prompt explains regression detection."""
        assert "regression" in SYSTEM_PROMPT.lower()

    def test_system_prompt_has_examples(self):
        """System prompt includes examples."""
        assert "example" in SYSTEM_PROMPT.lower()


class TestRegressionAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return RegressionResult."""
        assert agent._output_type == RegressionResult

    def test_agent_has_no_deps_type(self):
        """Regression agent doesn't need file access."""
        # It only analyzes dockerfile content passed in prompt
        assert agent._deps_type is None or agent._deps_type == type(None)


class TestRegressionResult:
    """Test RegressionResult model."""

    def test_regression_result_no_regression(self):
        """RegressionResult for no regression."""
        result = RegressionResult(
            has_regression=False,
            violations=[],
            adjusted_confidence=8,
        )
        assert result.has_regression is False
        assert result.violations == []
        assert result.adjusted_confidence == 8

    def test_regression_result_with_regression(self):
        """RegressionResult when regression detected."""
        result = RegressionResult(
            has_regression=True,
            violations=["Removed ARG DATABASE_URL", "Changed back to alpine"],
            adjusted_confidence=3,
        )
        assert result.has_regression is True
        assert len(result.violations) == 2
        assert result.adjusted_confidence == 3

    def test_confidence_range(self):
        """Confidence must be 0-10."""
        result = RegressionResult(
            has_regression=False,
            violations=[],
            adjusted_confidence=10,
        )
        assert 0 <= result.adjusted_confidence <= 10

    def test_violations_default_empty(self):
        """violations defaults to empty list."""
        result = RegressionResult(
            has_regression=False,
            adjusted_confidence=5,
        )
        assert result.violations == []


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_new_dockerfile(self):
        """Template renders new dockerfile."""
        rendered = USER_PROMPT.render(
            dockerfile="FROM node:20\nWORKDIR /app",
            historical_fixes=[],
            original_confidence=8,
        )
        assert "FROM node:20" in rendered
        assert "WORKDIR /app" in rendered

    def test_renders_historical_fixes(self):
        """Template renders historical fixes."""
        fixes = [
            {"explanation": "Added ARG for secrets", "fix": "ARG DATABASE_URL", "error": None},
            {"explanation": "Changed to non-alpine", "fix": "FROM node:20", "error": "native deps failed"},
        ]
        rendered = USER_PROMPT.render(
            dockerfile="FROM node:20",
            historical_fixes=fixes,
            original_confidence=7,
        )
        assert "ARG for secrets" in rendered
        assert "non-alpine" in rendered
        assert "native deps failed" in rendered

    def test_renders_original_confidence(self):
        """Template includes original confidence."""
        rendered = USER_PROMPT.render(
            dockerfile="FROM node:20",
            historical_fixes=[],
            original_confidence=9,
        )
        assert "9" in rendered


class TestRegressionAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_no_regression_preserves_confidence(self):
        """No regression keeps original confidence."""
        mock_result = RegressionResult(
            has_regression=False,
            violations=[],
            adjusted_confidence=8,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert result.output.has_regression is False
            assert result.output.adjusted_confidence == 8

    @pytest.mark.asyncio
    async def test_regression_caps_confidence(self):
        """Regression detected caps confidence at 3."""
        mock_result = RegressionResult(
            has_regression=True,
            violations=["Removed ARG DATABASE_URL"],
            adjusted_confidence=3,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert result.output.has_regression is True
            assert result.output.adjusted_confidence == 3
            assert "ARG DATABASE_URL" in result.output.violations[0]

    @pytest.mark.asyncio
    async def test_multiple_violations(self):
        """Agent can detect multiple regressions."""
        mock_result = RegressionResult(
            has_regression=True,
            violations=[
                "Removed ARG DATABASE_URL",
                "Changed FROM node:20 back to node:20-alpine",
                "Removed RUN npm ci --only=production",
            ],
            adjusted_confidence=2,
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)

            result = await agent.run("test prompt")

            assert len(result.output.violations) == 3

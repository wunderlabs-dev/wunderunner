"""Integration tests for dockerfile generation activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import dockerfile
from wunderunner.exceptions import DockerfileError
from wunderunner.models.generation import DockerfileResult
from wunderunner.workflows.state import Learning, Phase


class TestGenerateActivity:
    """Integration tests for dockerfile.generate()."""

    @pytest.mark.asyncio
    async def test_fresh_generation_returns_dockerfile(self, node_analysis, tmp_path):
        """Fresh generation returns valid GenerateResult."""
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nWORKDIR /app",
            confidence=8,
            reasoning="Standard Node.js setup",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = [{"role": "assistant", "content": "..."}]

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            assert result.result.dockerfile == "FROM node:20-slim\nWORKDIR /app"
            assert result.result.confidence == 8
            assert len(result.messages) > 0

    @pytest.mark.asyncio
    async def test_refinement_uses_existing_dockerfile(self, node_analysis, tmp_path):
        """Refinement passes existing Dockerfile to agent."""
        existing = "FROM node:18-slim\nWORKDIR /app\n"
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nWORKDIR /app\n",
            confidence=9,
            reasoning="Upgraded to Node 20",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=existing,
                project_path=tmp_path,
            )

            # Verify existing was passed to prompt render
            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("existing_dockerfile") == existing

    @pytest.mark.asyncio
    async def test_learnings_passed_to_agent(self, node_analysis, tmp_path):
        """Learnings from previous attempts are passed to agent."""
        learnings = [
            Learning(
                phase=Phase.BUILD,
                error_type="BuildError",
                error_message="npm ERR! Missing script",
            )
        ]
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=7,
            reasoning="Fixed build script issue",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                node_analysis,
                learnings=learnings,
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("learnings") == learnings

    @pytest.mark.asyncio
    async def test_hints_passed_to_agent(self, node_analysis, tmp_path):
        """User hints are passed to agent."""
        hints = ["Use node:20-slim as base image"]
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=9,
            reasoning="Used suggested base image",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=hints,
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("hints") == hints

    @pytest.mark.asyncio
    async def test_message_history_preserved(self, node_analysis, tmp_path):
        """Message history is passed and updated for stateful conversation."""
        previous_messages = [{"role": "user", "content": "previous"}]
        new_messages = [{"role": "assistant", "content": "new response"}]

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=8,
            reasoning="Continued conversation",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = new_messages

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
                message_history=previous_messages,
            )

            # Verify history was passed to agent
            call_kwargs = mock_agent.agent.run.call_args.kwargs
            assert call_kwargs.get("message_history") == previous_messages

            # Verify new messages returned
            assert result.messages == new_messages

    @pytest.mark.asyncio
    async def test_agent_error_raises_dockerfile_error(self, node_analysis, tmp_path):
        """Agent failure raises DockerfileError."""
        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API timeout"))
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            with pytest.raises(DockerfileError, match="Failed to generate"):
                await dockerfile.generate(
                    node_analysis,
                    learnings=[],
                    hints=[],
                    existing=None,
                    project_path=tmp_path,
                )

    @pytest.mark.asyncio
    async def test_secrets_extracted_from_analysis(self, analysis_with_secrets, tmp_path):
        """Secrets are extracted and passed to agent prompt."""
        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\nARG DATABASE_URL\nARG API_KEY\n",
            confidence=8,
            reasoning="Added secret ARGs",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await dockerfile.generate(
                analysis_with_secrets,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            secrets = call_kwargs.get("secrets", [])
            secret_names = [s.name for s in secrets]
            assert "DATABASE_URL" in secret_names
            assert "API_KEY" in secret_names
            # PORT is not a secret
            assert "PORT" not in secret_names


class TestRegressionCheck:
    """Tests for regression detection during generation."""

    @pytest.mark.asyncio
    async def test_regression_detected_adjusts_confidence(self, node_analysis, tmp_path):
        """Regression detection lowers confidence and adds warning."""
        from wunderunner.agents.validation.regression import RegressionResult
        from wunderunner.models.context import ContextEntry, EntryType

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:18-slim\n",  # Old version
            confidence=8,
            reasoning="Generated dockerfile",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        mock_regression = RegressionResult(
            has_regression=True,
            violations=["Reverted to node:18 from node:20"],
            adjusted_confidence=4,
        )
        mock_regression_result = MagicMock()
        mock_regression_result.output = mock_regression

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            fix="Upgraded to node:20-slim",
            explanation="Node 20 required for ESM support",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]
        mock_context.violation_count = 0

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.regression_agent") as mock_reg_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.activities.dockerfile.save_context", new_callable=AsyncMock),
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            mock_reg_agent.USER_PROMPT.render.return_value = "regression prompt"
            mock_reg_agent.agent.run = AsyncMock(return_value=mock_regression_result)

            mock_load.return_value = mock_context

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            # Confidence should be lowered
            assert result.result.confidence == 4
            # Reasoning should include regression warning
            assert "REGRESSION" in result.result.reasoning

    @pytest.mark.asyncio
    async def test_no_regression_keeps_original_result(self, node_analysis, tmp_path):
        """No regression keeps original confidence."""
        from wunderunner.agents.validation.regression import RegressionResult
        from wunderunner.models.context import ContextEntry, EntryType

        mock_dockerfile_result = DockerfileResult(
            dockerfile="FROM node:20-slim\n",
            confidence=9,
            reasoning="Good dockerfile",
        )
        mock_result = MagicMock()
        mock_result.output = mock_dockerfile_result
        mock_result.new_messages.return_value = []

        mock_regression = RegressionResult(
            has_regression=False,
            violations=[],
            adjusted_confidence=9,
        )
        mock_regression_result = MagicMock()
        mock_regression_result.output = mock_regression

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            fix="Previous fix",
            explanation="Details",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]

        with (
            patch("wunderunner.activities.dockerfile.dockerfile_agent") as mock_agent,
            patch("wunderunner.activities.dockerfile.regression_agent") as mock_reg_agent,
            patch("wunderunner.activities.dockerfile.get_fallback_model"),
            patch("wunderunner.activities.dockerfile.load_context", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.activities.dockerfile.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.get_runtime_template.return_value = "node template"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)

            mock_reg_agent.USER_PROMPT.render.return_value = "regression prompt"
            mock_reg_agent.agent.run = AsyncMock(return_value=mock_regression_result)

            mock_load.return_value = mock_context

            result = await dockerfile.generate(
                node_analysis,
                learnings=[],
                hints=[],
                existing=None,
                project_path=tmp_path,
            )

            # Original confidence preserved
            assert result.result.confidence == 9
            assert "REGRESSION" not in result.result.reasoning

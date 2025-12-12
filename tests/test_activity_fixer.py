"""Integration tests for fixer/improvement activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.activities import fixer
from wunderunner.models.generation import ImprovementResult
from wunderunner.workflows.state import Learning, Phase


class TestImproveDockerfile:
    """Integration tests for fixer.improve_dockerfile()."""

    @pytest.mark.asyncio
    async def test_improvement_returns_fixed_dockerfile(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Improvement returns fixed Dockerfile with confidence."""
        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\nRUN npm install",
            confidence=7,
            reasoning="Added missing npm install step",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            assert result.dockerfile == "FROM node:20-slim\nRUN npm install"
            assert result.confidence == 7
            assert "npm install" in result.reasoning

    @pytest.mark.asyncio
    async def test_improvement_can_modify_project_files(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Improvement agent can modify project files."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=8,
            reasoning="Removed conflicting .babelrc",
            files_modified=[".babelrc"],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            assert ".babelrc" in result.files_modified

    @pytest.mark.asyncio
    async def test_agent_error_returns_unchanged_dockerfile(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Agent failure returns original Dockerfile with zero confidence."""
        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(side_effect=RuntimeError("API error"))
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            result = await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            # Should return unchanged Dockerfile (strip trailing newline for comparison)
            assert result.dockerfile.strip() == valid_dockerfile.strip()
            assert result.confidence == 0
            assert "error" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_attempt_number_passed_to_prompt(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Attempt number is passed to agent for context."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=5,
            reasoning="Attempt 3 fix",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=3,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("attempt_number") == 3

    @pytest.mark.asyncio
    async def test_timeout_error_sets_exit_code_124(
        self, node_analysis, valid_dockerfile, tmp_path
    ):
        """Timeout errors set exit_code to 124."""
        timeout_learning = Learning(
            phase=Phase.HEALTHCHECK,
            error_type="HealthcheckError",
            error_message="Container timeout waiting for health",
        )
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=6,
            reasoning="Fixed timeout issue",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=timeout_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("exit_code") == 124

    @pytest.mark.asyncio
    async def test_historical_fixes_passed_for_antiregression(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Historical fixes are passed to agent for anti-regression."""
        from wunderunner.models.context import ContextEntry, EntryType

        historical_fix = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            error="Previous build error",
            fix="Added npm ci",
            explanation="npm ci is faster than npm install",
        )
        mock_context = MagicMock()
        mock_context.get_dockerfile_fixes.return_value = [historical_fix]

        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=7,
            reasoning="Applied fix",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock),
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = mock_context

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            call_kwargs = mock_agent.USER_PROMPT.render.call_args.kwargs
            assert call_kwargs.get("historical_fixes") == [historical_fix]

    @pytest.mark.asyncio
    async def test_improvement_recorded_to_context(
        self, node_analysis, valid_dockerfile, build_learning, tmp_path
    ):
        """Successful improvement is recorded to context storage."""
        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,
            confidence=8,
            reasoning="Fixed the issue",
            files_modified=[],
        )
        mock_result = MagicMock()
        mock_result.output = mock_improvement

        with (
            patch("wunderunner.activities.fixer.improvement_agent") as mock_agent,
            patch("wunderunner.activities.fixer.get_fallback_model"),
            patch("wunderunner.activities.fixer.load_context", new_callable=AsyncMock) as mock_ctx,
            patch("wunderunner.activities.fixer.add_entry", new_callable=AsyncMock) as mock_add,
        ):
            mock_agent.USER_PROMPT.render.return_value = "test prompt"
            mock_agent.agent.run = AsyncMock(return_value=mock_result)
            mock_ctx.return_value = MagicMock(get_dockerfile_fixes=lambda: [])

            await fixer.improve_dockerfile(
                learning=build_learning,
                analysis=node_analysis,
                dockerfile_content=valid_dockerfile,
                compose_content=None,
                project_path=tmp_path,
                attempt_number=1,
            )

            # Verify entry was added to context
            mock_add.assert_called_once()
            call_args = mock_add.call_args
            assert call_args[0][0] == tmp_path  # project_path
            entry = call_args[0][1]
            assert "confidence 8" in entry.fix

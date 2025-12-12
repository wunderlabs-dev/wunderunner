"""Integration tests for workflow nodes."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import GraphRunContext

from wunderunner.workflows.containerize import (
    Analyze,
    Build,
    CollectSecrets,
    Dockerfile,
    Healthcheck,
    HumanHint,
    ImproveDockerfile,
    RetryOrHint,
    Services,
    Start,
    Validate,
)
from wunderunner.workflows.state import ContainerizeState, Learning, Phase, Severity


@pytest.fixture
def mock_ctx(workflow_state):
    """Create a mock GraphRunContext."""
    ctx = MagicMock(spec=GraphRunContext)
    ctx.state = workflow_state
    return ctx


class TestAnalyzeNode:
    """Tests for Analyze workflow node."""

    @pytest.mark.asyncio
    async def test_analyze_sets_analysis_on_state(self, mock_ctx, node_analysis):
        """Analyze node sets analysis result on state."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = node_analysis

            node = Analyze()
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.analysis == node_analysis
            # Should return Dockerfile node (no secrets)
            assert isinstance(next_node, Dockerfile)

    @pytest.mark.asyncio
    async def test_analyze_with_secrets_returns_collect_secrets(
        self, mock_ctx, analysis_with_secrets
    ):
        """Analyze with secrets returns CollectSecrets node."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = analysis_with_secrets

            node = Analyze()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, CollectSecrets)

    @pytest.mark.asyncio
    async def test_analyze_reports_progress(self, mock_ctx, node_analysis, progress_messages):
        """Analyze node reports progress via callback."""
        with patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = node_analysis

            node = Analyze()
            await node.run(mock_ctx)

            # Should have progress messages
            assert len(progress_messages) >= 2
            severities = [s for s, _ in progress_messages]
            assert Severity.INFO in severities
            assert Severity.SUCCESS in severities


class TestCollectSecretsNode:
    """Tests for CollectSecrets workflow node."""

    @pytest.mark.asyncio
    async def test_collects_secrets_via_callback(self, mock_ctx, analysis_with_secrets):
        """CollectSecrets prompts for each secret via callback."""
        mock_ctx.state.analysis = analysis_with_secrets

        secret_prompts = []
        def mock_secret_prompt(name: str, service: str | None) -> str:
            secret_prompts.append((name, service))
            return f"value_for_{name}"

        mock_ctx.state.on_secret_prompt = mock_secret_prompt

        node = CollectSecrets()
        next_node = await node.run(mock_ctx)

        # Should have prompted for each secret
        assert len(secret_prompts) == 2  # DATABASE_URL, API_KEY
        secret_names = [name for name, _ in secret_prompts]
        assert "DATABASE_URL" in secret_names
        assert "API_KEY" in secret_names

        # Values should be stored
        assert mock_ctx.state.secret_values["DATABASE_URL"] == "value_for_DATABASE_URL"
        assert mock_ctx.state.secret_values["API_KEY"] == "value_for_API_KEY"

        # Should return Dockerfile node
        assert isinstance(next_node, Dockerfile)


class TestDockerfileNode:
    """Tests for Dockerfile workflow node."""

    @pytest.mark.asyncio
    async def test_generates_dockerfile_on_state(self, mock_ctx, node_analysis):
        """Dockerfile node generates and stores content."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        mock_ctx.state.analysis = node_analysis
        mock_result = GenerateResult(
            result=DockerfileResult(
                dockerfile="FROM node:20-slim\n",
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_result

            node = Dockerfile()
            next_node = await node.run(mock_ctx)

            assert "FROM node:20-slim" in mock_ctx.state.dockerfile_content
            assert mock_ctx.state.last_confidence == 8
            assert isinstance(next_node, Validate)

    @pytest.mark.asyncio
    async def test_dockerfile_error_returns_retry_or_hint(self, mock_ctx, node_analysis):
        """Dockerfile generation error returns RetryOrHint."""
        from wunderunner.exceptions import DockerfileError

        mock_ctx.state.analysis = node_analysis

        with patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = DockerfileError("Generation failed")

            node = Dockerfile()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, RetryOrHint)
            assert len(mock_ctx.state.learnings) == 1
            assert mock_ctx.state.learnings[0].phase == Phase.DOCKERFILE


class TestValidateNode:
    """Tests for Validate workflow node."""

    @pytest.mark.asyncio
    async def test_valid_returns_services(self, mock_ctx, node_analysis, passing_validation):
        """Valid Dockerfile returns Services node."""
        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"

        with patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = passing_validation

            node = Validate()
            next_node = await node.run(mock_ctx)

            assert mock_ctx.state.last_validation_grade == 85
            assert isinstance(next_node, Services)

    @pytest.mark.asyncio
    async def test_invalid_returns_retry_or_hint(self, mock_ctx, node_analysis, failing_validation):
        """Invalid Dockerfile returns RetryOrHint."""
        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"

        with patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = failing_validation

            node = Validate()
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, RetryOrHint)
            assert mock_ctx.state.last_validation_grade == 45


class TestRetryOrHintNode:
    """Tests for RetryOrHint decision node."""

    @pytest.mark.asyncio
    async def test_runtime_error_returns_improve_dockerfile(self, mock_ctx, build_learning):
        """Runtime phase error (build/start/healthcheck) returns ImproveDockerfile."""
        mock_ctx.state.retry_count = 0

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, ImproveDockerfile)
            assert mock_ctx.state.retry_count == 1

    @pytest.mark.asyncio
    async def test_validation_error_returns_dockerfile(self, mock_ctx, validation_learning):
        """Validation phase error returns Dockerfile for regeneration."""
        mock_ctx.state.retry_count = 0

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=validation_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, Dockerfile)
            assert mock_ctx.state.retry_count == 1

    @pytest.mark.asyncio
    async def test_max_attempts_returns_human_hint(self, mock_ctx, build_learning):
        """Exceeding max attempts returns HumanHint."""
        mock_ctx.state.retry_count = 2

        with patch("wunderunner.workflows.containerize.get_settings") as mock_settings:
            mock_settings.return_value.max_attempts = 3

            node = RetryOrHint(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert isinstance(next_node, HumanHint)


class TestHumanHintNode:
    """Tests for HumanHint workflow node."""

    @pytest.mark.asyncio
    async def test_hint_provided_returns_dockerfile(self, mock_ctx):
        """User hint resets retry count and returns Dockerfile."""
        mock_ctx.state.retry_count = 3
        mock_ctx.state.learnings = [
            Learning(phase=Phase.BUILD, error_type="BuildError", error_message="Failed")
        ]
        mock_ctx.state.on_hint_prompt = lambda learnings: "Try using alpine base"

        node = HumanHint()
        next_node = await node.run(mock_ctx)

        assert isinstance(next_node, Dockerfile)
        assert mock_ctx.state.retry_count == 0
        assert "Try using alpine base" in mock_ctx.state.hints

    @pytest.mark.asyncio
    async def test_no_hint_raises_keyboard_interrupt(self, mock_ctx):
        """No hint (None) raises KeyboardInterrupt to quit."""
        mock_ctx.state.learnings = []
        mock_ctx.state.on_hint_prompt = lambda learnings: None

        node = HumanHint()

        with pytest.raises(KeyboardInterrupt):
            await node.run(mock_ctx)


class TestImproveDockerfileNode:
    """Tests for ImproveDockerfile workflow node."""

    @pytest.mark.asyncio
    async def test_improvement_updates_state(self, mock_ctx, node_analysis, build_learning):
        """Improvement updates Dockerfile content and confidence."""
        from wunderunner.models.generation import ImprovementResult

        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:18-slim\n"
        mock_ctx.state.retry_count = 1

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\n",
            confidence=7,
            reasoning="Upgraded Node version",
            files_modified=[],
        )

        with (
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fix,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
        ):
            mock_fix.return_value = mock_improvement
            mock_settings.return_value.max_attempts = 3

            node = ImproveDockerfile(learning=build_learning)
            next_node = await node.run(mock_ctx)

            assert "FROM node:20-slim" in mock_ctx.state.dockerfile_content
            assert mock_ctx.state.last_confidence == 7
            assert isinstance(next_node, Validate)

    @pytest.mark.asyncio
    async def test_compose_modification_skips_services_regen(
        self, mock_ctx, node_analysis, build_learning
    ):
        """Compose file modification sets skip_services_regen flag."""
        from wunderunner.models.generation import ImprovementResult

        mock_ctx.state.analysis = node_analysis
        mock_ctx.state.dockerfile_content = "FROM node:20-slim\n"
        mock_ctx.state.retry_count = 1

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\n",
            confidence=8,
            reasoning="Fixed compose",
            files_modified=["docker-compose.yaml"],
        )

        with (
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fix,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
        ):
            mock_fix.return_value = mock_improvement
            mock_settings.return_value.max_attempts = 3

            node = ImproveDockerfile(learning=build_learning)
            next_node = await node.run(mock_ctx)

            # Should skip to Build instead of Validate
            assert isinstance(next_node, Build)
            # Flag should be reset after use
            assert mock_ctx.state.skip_services_regen is False

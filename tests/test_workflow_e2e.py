"""End-to-end integration tests for containerize workflow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.workflows.containerize import Analyze, Success, containerize_graph
from wunderunner.workflows.state import ContainerizeState, Severity


class TestWorkflowHappyPath:
    """End-to-end tests for successful workflow execution."""

    @pytest.mark.asyncio
    async def test_full_workflow_success(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Full workflow completes successfully with all mocked activities."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        progress_messages = []

        def track_progress(severity: Severity, message: str) -> None:
            progress_messages.append((severity, message))

        state = ContainerizeState(
            path=tmp_path,
            on_progress=track_progress,
        )

        # Mock all activities
        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with (
            # Analysis
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            # Dockerfile generation
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            # Validation
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            # Services generation
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            # Docker build
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            # Start containers
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            # Healthcheck
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            # File write
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose

            from wunderunner.activities.docker import BuildResult
            mock_build.return_value = BuildResult(image_id="sha256:abc", cache_hit=False)
            mock_start.return_value = ["container1"]
            mock_health.return_value = None  # Success

            # Mock aiofiles context manager
            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            # Run workflow
            result = await containerize_graph.run(Analyze(), state=state)

            # Verify success
            assert isinstance(result.output, Success)

            # Verify all activities were called
            mock_analyze.assert_called_once()
            mock_dockerfile.assert_called_once()
            mock_validate.assert_called_once()
            mock_services.assert_called_once()
            mock_build.assert_called_once()
            mock_start.assert_called_once()
            mock_health.assert_called_once()

            # Verify progress messages include success indicators
            severities = [s for s, _ in progress_messages]
            assert Severity.SUCCESS in severities

    @pytest.mark.asyncio
    async def test_workflow_with_secrets_collects_them(
        self,
        tmp_path,
        analysis_with_secrets,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Workflow with secrets prompts for and collects them."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.models.generation import DockerfileResult

        collected_secrets = {}

        def secret_prompt(name: str, service: str | None) -> str:
            value = f"secret_value_for_{name}"
            collected_secrets[name] = value
            return value

        state = ContainerizeState(
            path=tmp_path,
            on_secret_prompt=secret_prompt,
        )

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = analysis_with_secrets
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose

            from wunderunner.activities.docker import BuildResult
            mock_build.return_value = BuildResult(image_id="sha256:abc", cache_hit=False)
            mock_start.return_value = ["container1"]
            mock_health.return_value = None

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(Analyze(), state=state)

            assert isinstance(result.output, Success)

            # Verify secrets were collected
            assert "DATABASE_URL" in collected_secrets
            assert "API_KEY" in collected_secrets

            # Verify secrets are stored on state
            assert state.secret_values["DATABASE_URL"] == "secret_value_for_DATABASE_URL"


class TestWorkflowErrorRecovery:
    """Tests for workflow error recovery paths."""

    @pytest.mark.asyncio
    async def test_build_error_triggers_improvement(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Build error triggers improvement agent and retry."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.activities.docker import BuildResult
        from wunderunner.exceptions import BuildError
        from wunderunner.models.generation import DockerfileResult, ImprovementResult

        state = ContainerizeState(path=tmp_path)

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        mock_improvement = ImprovementResult(
            dockerfile="FROM node:20-slim\nRUN npm install\n",
            confidence=7,
            reasoning="Fixed build",
            files_modified=[],
        )

        build_call_count = 0

        async def mock_build_with_failure(*args, **kwargs):
            nonlocal build_call_count
            build_call_count += 1
            if build_call_count == 1:
                raise BuildError("npm install failed")
            return BuildResult(image_id="sha256:abc", cache_hit=False)

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fixer,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose
            mock_build.side_effect = mock_build_with_failure
            mock_fixer.return_value = mock_improvement
            mock_start.return_value = ["container1"]
            mock_health.return_value = None
            mock_settings.return_value.max_attempts = 3

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(Analyze(), state=state)

            # Should eventually succeed
            assert isinstance(result.output, Success)

            # Fixer should have been called
            mock_fixer.assert_called_once()

            # Build should have been called twice
            assert build_call_count == 2

            # Learnings should include build error
            assert len(state.learnings) >= 1
            assert any(l.phase.value == "build" for l in state.learnings)

    @pytest.mark.asyncio
    async def test_max_retries_triggers_human_hint(
        self,
        tmp_path,
        node_analysis,
        valid_dockerfile,
        valid_compose,
        passing_validation,
    ):
        """Exceeding max retries asks for human hint."""
        from wunderunner.activities.dockerfile import GenerateResult
        from wunderunner.activities.docker import BuildResult
        from wunderunner.exceptions import BuildError
        from wunderunner.models.generation import DockerfileResult, ImprovementResult

        hint_requested = []

        def hint_prompt(learnings):
            hint_requested.append(learnings)
            return "Use node:20-alpine instead"

        state = ContainerizeState(
            path=tmp_path,
            on_hint_prompt=hint_prompt,
        )

        mock_dockerfile_result = GenerateResult(
            result=DockerfileResult(
                dockerfile=valid_dockerfile,
                confidence=8,
                reasoning="Good dockerfile",
            ),
            messages=[],
        )

        mock_improvement = ImprovementResult(
            dockerfile=valid_dockerfile,  # Still fails
            confidence=3,
            reasoning="Not sure",
            files_modified=[],
        )

        build_call_count = 0

        async def mock_build_with_failures(*args, **kwargs):
            nonlocal build_call_count
            build_call_count += 1
            if build_call_count <= 3:
                raise BuildError(f"Build failed attempt {build_call_count}")
            return BuildResult(image_id="sha256:abc", cache_hit=False)

        with (
            patch("wunderunner.workflows.containerize.project.analyze", new_callable=AsyncMock) as mock_analyze,
            patch("wunderunner.workflows.containerize.dockerfile.generate", new_callable=AsyncMock) as mock_dockerfile,
            patch("wunderunner.workflows.containerize.validation.validate", new_callable=AsyncMock) as mock_validate,
            patch("wunderunner.workflows.containerize.services.generate", new_callable=AsyncMock) as mock_services,
            patch("wunderunner.workflows.containerize.docker.build", new_callable=AsyncMock) as mock_build,
            patch("wunderunner.workflows.containerize.fixer.improve_dockerfile", new_callable=AsyncMock) as mock_fixer,
            patch("wunderunner.workflows.containerize.services.start", new_callable=AsyncMock) as mock_start,
            patch("wunderunner.workflows.containerize.services.healthcheck", new_callable=AsyncMock) as mock_health,
            patch("wunderunner.workflows.containerize.get_settings") as mock_settings,
            patch("aiofiles.open", new_callable=MagicMock) as mock_aiofiles,
        ):
            mock_analyze.return_value = node_analysis
            mock_dockerfile.return_value = mock_dockerfile_result
            mock_validate.return_value = passing_validation
            mock_services.return_value = valid_compose
            mock_build.side_effect = mock_build_with_failures
            mock_fixer.return_value = mock_improvement
            mock_start.return_value = ["container1"]
            mock_health.return_value = None
            mock_settings.return_value.max_attempts = 3

            mock_file = AsyncMock()
            mock_aiofiles.return_value.__aenter__.return_value = mock_file

            result = await containerize_graph.run(Analyze(), state=state)

            # Should eventually succeed after human hint
            assert isinstance(result.output, Success)

            # Human hint should have been requested
            assert len(hint_requested) >= 1

            # Hint should be stored in state
            assert "Use node:20-alpine instead" in state.hints

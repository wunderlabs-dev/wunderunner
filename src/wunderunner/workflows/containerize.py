"""Containerize workflow using Pydantic Graph."""

from __future__ import annotations

from dataclasses import dataclass

import aiofiles
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from wunderunner.activities import docker, dockerfile, fixer, project, services, validation
from wunderunner.exceptions import (
    BuildError,
    DockerfileError,
    HealthcheckError,
    ServicesError,
    StartError,
    ValidationError,
)
from wunderunner.settings import get_settings
from wunderunner.workflows.state import ContainerizeState, Learning, Phase, Severity

Ctx = GraphRunContext[ContainerizeState, None]


@dataclass
class Success:
    """Workflow completed successfully."""


@dataclass
class Analyze(BaseNode[ContainerizeState]):
    """Run analysis agents and check for secrets."""

    async def run(self, ctx: Ctx) -> CollectSecrets | Dockerfile:
        progress = ctx.state.on_progress
        progress(Severity.INFO, "Analyzing project...")
        analysis = await project.analyze(ctx.state.path, ctx.state.rebuild)
        ctx.state.analysis = analysis

        runtime = analysis.project_structure.runtime
        framework = analysis.project_structure.framework or "no framework"
        progress(Severity.SUCCESS, f"Detected {runtime} ({framework})")

        secrets = [v for v in analysis.env_vars if v.secret]
        if secrets:
            return CollectSecrets()
        return Dockerfile()


@dataclass
class CollectSecrets(BaseNode[ContainerizeState]):
    """Prompt user for secret values via callback."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        progress = ctx.state.on_progress
        secret_prompt = ctx.state.on_secret_prompt
        secrets = [v for v in ctx.state.analysis.env_vars if v.secret]

        progress(Severity.INFO, f"Collecting {len(secrets)} secret(s)...")
        for var in secrets:
            value = secret_prompt(var.name, var.service)
            ctx.state.secret_values[var.name] = value

        progress(Severity.SUCCESS, "Secrets collected")
        return Dockerfile()


@dataclass
class Dockerfile(BaseNode[ContainerizeState]):
    """Generate or refine Dockerfile."""

    async def run(self, ctx: Ctx) -> Validate | RetryOrHint:
        progress = ctx.state.on_progress
        is_refine = ctx.state.dockerfile_content is not None
        action = "Refining" if is_refine else "Generating"

        try:
            progress(Severity.INFO, f"{action} Dockerfile...")
            gen_result = await dockerfile.generate(
                ctx.state.analysis,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.dockerfile_content,
                project_path=ctx.state.path,
                message_history=ctx.state.dockerfile_messages,
            )

            # Store results and conversation history for next retry
            ctx.state.dockerfile_content = gen_result.result.dockerfile
            ctx.state.last_confidence = gen_result.result.confidence
            ctx.state.dockerfile_messages = gen_result.messages

            # Report confidence level
            conf = gen_result.result.confidence
            has_regression = "REGRESSION" in gen_result.result.reasoning

            status_msg = f"Dockerfile {action.lower()[:-3]}ed (confidence: {conf}/10)"
            if has_regression:
                status_msg += " - regression detected"

            if conf >= 7 and not has_regression:
                progress(Severity.SUCCESS, status_msg)
            elif conf >= 4:
                progress(Severity.WARNING, status_msg)
            else:
                progress(Severity.WARNING, status_msg)

            return Validate()
        except DockerfileError as e:
            progress(Severity.ERROR, "Dockerfile generation failed")
            learning = Learning(
                phase=Phase.DOCKERFILE,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Validate(BaseNode[ContainerizeState]):
    """Validate Dockerfile using two-tier validation (programmatic + LLM grading)."""

    async def run(self, ctx: Ctx) -> Services | RetryOrHint:
        progress = ctx.state.on_progress

        try:
            progress(Severity.INFO, "Validating Dockerfile...")
            result = await validation.validate(
                ctx.state.dockerfile_content,
                ctx.state.analysis,
                ctx.state.learnings,
            )

            ctx.state.last_validation_grade = result.grade

            if result.is_valid:
                progress(Severity.SUCCESS, f"Validation passed (grade: {result.grade}/100)")
                return Services()

            progress(Severity.WARNING, f"Validation failed (grade: {result.grade}/100)")
            issues_text = "; ".join(result.issues) if result.issues else result.feedback
            learning = Learning(
                phase=Phase.VALIDATION,
                error_type="ValidationFailed",
                error_message=f"Grade: {result.grade}/100. {issues_text}",
                context="\n".join(result.recommendations) if result.recommendations else None,
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)

        except ValidationError as e:
            progress(Severity.ERROR, f"Validation error: {e}")
            learning = Learning(
                phase=Phase.VALIDATION,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Services(BaseNode[ContainerizeState]):
    """Generate or refine docker-compose.yaml."""

    async def run(self, ctx: Ctx) -> Build | RetryOrHint:
        progress = ctx.state.on_progress
        is_refine = ctx.state.compose_content is not None
        action = "Refining" if is_refine else "Generating"

        try:
            progress(Severity.INFO, f"{action} docker-compose.yaml...")
            ctx.state.compose_content = await services.generate(
                ctx.state.analysis,
                ctx.state.dockerfile_content,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.compose_content,
                project_path=ctx.state.path,
            )

            compose_path = ctx.state.path / "docker-compose.yaml"
            async with aiofiles.open(compose_path, "w") as f:
                await f.write(ctx.state.compose_content)

            progress(Severity.SUCCESS, f"docker-compose.yaml {action.lower()[:-3]}ed")
            return Build()
        except ServicesError as e:
            progress(Severity.ERROR, "Compose generation failed")
            learning = Learning(
                phase=Phase.SERVICES,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Build(BaseNode[ContainerizeState]):
    """Build Docker image."""

    async def run(self, ctx: Ctx) -> Start | RetryOrHint:
        progress = ctx.state.on_progress

        try:
            progress(Severity.INFO, "Building Docker image...")
            build_result = await docker.build(
                ctx.state.path,
                ctx.state.dockerfile_content,
            )
            if build_result.cache_hit:
                progress(Severity.SUCCESS, "Docker image found in cache")
            else:
                progress(Severity.SUCCESS, "Docker image built")
            return Start()
        except BuildError as e:
            progress(Severity.ERROR, "Docker build failed")
            # Pass full build logs - the agent needs context to understand the error
            learning = Learning(
                phase=Phase.BUILD,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Start(BaseNode[ContainerizeState]):
    """Start containers with docker compose."""

    async def run(self, ctx: Ctx) -> Healthcheck | RetryOrHint:
        progress = ctx.state.on_progress

        try:
            progress(Severity.INFO, "Starting containers...")
            ctx.state.container_ids = await services.start(ctx.state.path)
            progress(Severity.SUCCESS, f"Started {len(ctx.state.container_ids)} container(s)")
            return Healthcheck()
        except StartError as e:
            progress(Severity.ERROR, "Failed to start containers")
            learning = Learning(
                phase=Phase.START,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Healthcheck(BaseNode[ContainerizeState]):
    """Check container health."""

    async def run(self, ctx: Ctx) -> End[Success] | RetryOrHint:
        progress = ctx.state.on_progress
        timeout = ctx.state.healthcheck_timeout

        try:
            progress(Severity.INFO, f"Checking container health (timeout: {timeout}s)...")
            await services.healthcheck(ctx.state.container_ids, timeout=timeout)
            progress(Severity.SUCCESS, "All containers healthy")
            return End(Success())
        except HealthcheckError as e:
            progress(Severity.ERROR, "Health check failed")
            # Don't increase timeout - if it times out, the app is likely broken
            # Increasing just wastes time. Keep fixed at 60s.
            learning = Learning(
                phase=Phase.HEALTHCHECK,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


_RUNTIME_PHASES = frozenset({Phase.BUILD, Phase.START, Phase.HEALTHCHECK})


@dataclass
class RetryOrHint(BaseNode[ContainerizeState]):
    """Decision: improve Dockerfile, auto-retry, or ask human for hint."""

    learning: Learning

    async def run(self, ctx: Ctx) -> ImproveDockerfile | Dockerfile | HumanHint:
        settings = get_settings()
        ctx.state.retry_count += 1

        if ctx.state.retry_count >= settings.max_attempts:
            return HumanHint()

        if self.learning.phase in _RUNTIME_PHASES:
            return ImproveDockerfile(learning=self.learning)

        remaining = settings.max_attempts - ctx.state.retry_count
        ctx.state.on_progress(Severity.INFO, f"Retrying... ({remaining} attempts remaining)")
        return Dockerfile()


@dataclass
class HumanHint(BaseNode[ContainerizeState]):
    """Show errors and prompt user for hint via callback."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        progress = ctx.state.on_progress
        hint_prompt = ctx.state.on_hint_prompt

        progress(Severity.ERROR, "Workflow needs help after multiple attempts")

        # Get hint via callback (passes recent learnings for context)
        recent_learnings = ctx.state.learnings[-3:]
        hint = hint_prompt(recent_learnings)

        if hint is None:
            raise KeyboardInterrupt()

        ctx.state.hints.append(hint)
        ctx.state.retry_count = 0
        return Dockerfile()


_COMPOSE_PATTERNS = ("docker-compose", "compose.yaml", "compose.yml")


def _is_compose_file(filename: str) -> bool:
    """Check if a filename is a compose file."""
    return any(p in filename for p in _COMPOSE_PATTERNS)


@dataclass
class ImproveDockerfile(BaseNode[ContainerizeState]):
    """Improve Dockerfile after build/runtime errors.

    This unified agent can fix both Dockerfile issues AND project configuration
    issues (like removing problematic .babelrc files).
    """

    learning: Learning

    async def run(self, ctx: Ctx) -> Validate | Build | HumanHint:
        progress = ctx.state.on_progress

        progress(Severity.INFO, "Analyzing and fixing error...")
        improvement = await fixer.improve_dockerfile(
            learning=self.learning,
            analysis=ctx.state.analysis,
            dockerfile_content=ctx.state.dockerfile_content,
            compose_content=ctx.state.compose_content,
            project_path=ctx.state.path,
            attempt_number=ctx.state.retry_count,
        )

        ctx.state.dockerfile_content = improvement.dockerfile
        ctx.state.last_confidence = improvement.confidence

        self._report_improvement(ctx, improvement)

        return self._decide_next_step(ctx, improvement)

    def _report_improvement(self, ctx: Ctx, improvement) -> None:
        """Log what the improvement agent did."""
        progress = ctx.state.on_progress
        conf = improvement.confidence

        if not improvement.files_modified:
            msg = f"Improved Dockerfile (confidence {conf}/10): {improvement.reasoning}"
            progress(Severity.INFO, msg)
            return

        progress(Severity.SUCCESS, f"Fixed (confidence {conf}/10): {improvement.reasoning}")
        for f in improvement.files_modified:
            progress(Severity.INFO, f"  Modified: {f}")

        if any(_is_compose_file(f) for f in improvement.files_modified):
            ctx.state.skip_services_regen = True

    def _decide_next_step(self, ctx: Ctx, improvement) -> Validate | Build | HumanHint:
        """Decide whether to retry, skip to build, or ask human."""
        progress = ctx.state.on_progress
        settings = get_settings()
        conf = improvement.confidence
        remaining = settings.max_attempts - ctx.state.retry_count

        if conf <= 2 and remaining <= 1:
            progress(Severity.WARNING, "Low confidence and out of retries - requesting help")
            return HumanHint()

        if conf <= 2:
            progress(Severity.WARNING, f"Low confidence fix, trying anyway... ({remaining} left)")
        else:
            progress(Severity.INFO, f"Retrying build... ({remaining} attempts remaining)")

        if ctx.state.skip_services_regen:
            ctx.state.skip_services_regen = False
            return Build()

        return Validate()


containerize_graph = Graph(
    nodes=[
        Analyze,
        CollectSecrets,
        Dockerfile,
        Validate,
        Services,
        Build,
        Start,
        Healthcheck,
        RetryOrHint,
        HumanHint,
        ImproveDockerfile,
    ],
    state_type=ContainerizeState,
    run_end_type=Success,
)

"""Containerize workflow using Pydantic Graph."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console
from rich.prompt import Prompt

from wunderunner.activities import docker, dockerfile, project, services, validation
from wunderunner.exceptions import (
    BuildError,
    DockerfileError,
    HealthcheckError,
    ServicesError,
    StartError,
    ValidationError,
)
from wunderunner.settings import get_settings
from wunderunner.workflows.state import ContainerizeState, Learning

Ctx = GraphRunContext[ContainerizeState, None]


@dataclass
class Success:
    """Workflow completed successfully."""


@dataclass
class Analyze(BaseNode[ContainerizeState]):
    """Run analysis agents and check for secrets."""

    async def run(self, ctx: Ctx) -> CollectSecrets | Dockerfile:
        analysis = await project.analyze(ctx.state.path, ctx.state.rebuild)
        ctx.state.analysis = analysis

        secrets = [v for v in analysis.env_vars if v.secret]
        if secrets:
            return CollectSecrets()
        return Dockerfile()


@dataclass
class CollectSecrets(BaseNode[ContainerizeState]):
    """Prompt user for secret values via CLI."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        console = Console()
        secrets = [v for v in ctx.state.analysis.env_vars if v.secret]

        console.print("\n[yellow]Secrets required:[/yellow]")
        for var in secrets:
            service_hint = f" ({var.service})" if var.service else ""
            value = Prompt.ask(
                f"  [bold]{var.name}[/bold]{service_hint}",
                password=True,
            )
            ctx.state.secret_values[var.name] = value

        return Dockerfile()


@dataclass
class Dockerfile(BaseNode[ContainerizeState]):
    """Generate or refine Dockerfile."""

    async def run(self, ctx: Ctx) -> Validate | RetryOrHint:
        try:
            ctx.state.dockerfile_content = await dockerfile.generate(
                ctx.state.analysis,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.dockerfile_content,
                project_path=ctx.state.path,
            )
            return Validate()
        except DockerfileError as e:
            learning = Learning(
                phase="dockerfile",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Validate(BaseNode[ContainerizeState]):
    """Validate Dockerfile using two-tier validation (programmatic + LLM grading)."""

    async def run(self, ctx: Ctx) -> Services | RetryOrHint:
        try:
            result = await validation.validate(
                ctx.state.dockerfile_content,
                ctx.state.analysis,
                ctx.state.learnings,
            )

            # Store validation result for debugging/logging
            ctx.state.last_validation_grade = result.grade

            if result.is_valid:
                return Services()

            # Validation failed - create learning from feedback
            issues_text = "; ".join(result.issues) if result.issues else result.feedback
            learning = Learning(
                phase="validation",
                error_type="ValidationFailed",
                error_message=f"Grade: {result.grade}/100. {issues_text}",
                context="\n".join(result.recommendations) if result.recommendations else None,
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)

        except ValidationError as e:
            learning = Learning(
                phase="validation",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Services(BaseNode[ContainerizeState]):
    """Generate or refine docker-compose.yaml."""

    async def run(self, ctx: Ctx) -> Build | RetryOrHint:
        try:
            ctx.state.compose_content = await services.generate(
                ctx.state.analysis,
                ctx.state.dockerfile_content,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.compose_content,
                project_path=ctx.state.path,
            )

            # Write compose file to disk for docker compose to use
            settings = get_settings()
            compose_path = ctx.state.path / settings.cache_dir / "docker-compose.yaml"
            compose_path.parent.mkdir(parents=True, exist_ok=True)
            compose_path.write_text(ctx.state.compose_content)

            return Build()
        except ServicesError as e:
            learning = Learning(
                phase="services",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Build(BaseNode[ContainerizeState]):
    """Build Docker image."""

    async def run(self, ctx: Ctx) -> Start | RetryOrHint:
        try:
            await docker.build(ctx.state.path, ctx.state.dockerfile_content)
            return Start()
        except BuildError as e:
            learning = Learning(
                phase="build",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Start(BaseNode[ContainerizeState]):
    """Start containers with docker compose."""

    async def run(self, ctx: Ctx) -> Healthcheck | RetryOrHint:
        try:
            ctx.state.container_ids = await services.start(ctx.state.path)
            return Healthcheck()
        except StartError as e:
            learning = Learning(
                phase="start",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Healthcheck(BaseNode[ContainerizeState]):
    """Check container health."""

    async def run(self, ctx: Ctx) -> End[Success] | RetryOrHint:
        try:
            await services.healthcheck(ctx.state.container_ids)
            return End(Success())
        except HealthcheckError as e:
            learning = Learning(
                phase="healthcheck",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class RetryOrHint(BaseNode[ContainerizeState]):
    """Decision: auto-retry or ask human for hint."""

    learning: Learning

    async def run(self, ctx: Ctx) -> Dockerfile | HumanHint:
        settings = get_settings()
        ctx.state.attempts_since_hint += 1

        if ctx.state.attempts_since_hint < settings.max_attempts:
            return Dockerfile()
        return HumanHint()


@dataclass
class HumanHint(BaseNode[ContainerizeState]):
    """Show errors and prompt user for hint."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        console = Console()

        console.print("\n[red bold]Workflow failed after multiple attempts[/red bold]\n")
        console.print("[yellow]Errors encountered:[/yellow]")
        for learning in ctx.state.learnings:
            console.print(f"  [{learning.phase}] {learning.error_message}")

        console.print()
        hint = Prompt.ask("[cyan]Any hints to help fix this?[/cyan]")

        ctx.state.hints.append(hint)
        ctx.state.attempts_since_hint = 0
        return Dockerfile()


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
    ],
    state_type=ContainerizeState,
    run_end_type=Success,
)

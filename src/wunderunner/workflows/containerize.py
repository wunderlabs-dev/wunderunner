"""Containerize workflow using Pydantic Graph."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
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
        console = ctx.state.console
        with console.status("[bold blue]Analyzing project..."):
            analysis = await project.analyze(ctx.state.path, ctx.state.rebuild)
        ctx.state.analysis = analysis

        runtime = analysis.project_structure.runtime
        framework = analysis.project_structure.framework or "no framework"
        console.print(f"  [green]✓[/green] Detected {runtime} ({framework})")

        secrets = [v for v in analysis.env_vars if v.secret]
        if secrets:
            return CollectSecrets()
        return Dockerfile()


@dataclass
class CollectSecrets(BaseNode[ContainerizeState]):
    """Prompt user for secret values via CLI."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        console = ctx.state.console
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
        console = ctx.state.console
        is_refine = ctx.state.dockerfile_content is not None
        action = "Refining" if is_refine else "Generating"

        try:
            with console.status(f"[bold blue]{action} Dockerfile..."):
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

            # Show confidence and any regression warnings
            conf = gen_result.result.confidence
            if conf >= 7:
                color = "green"
            elif conf >= 4:
                color = "yellow"
            else:
                color = "red"

            status = f"{action.lower()[:-3]}ed (confidence: [{color}]{conf}/10[/{color}])"
            if "REGRESSION" in gen_result.result.reasoning:
                status += " [yellow]⚠ regression detected[/yellow]"
            console.print(f"  [green]✓[/green] Dockerfile {status}")

            return Validate()
        except DockerfileError as e:
            console.print("  [red]✗[/red] Dockerfile generation failed")
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
        console = ctx.state.console

        try:
            with console.status("[bold blue]Validating Dockerfile..."):
                result = await validation.validate(
                    ctx.state.dockerfile_content,
                    ctx.state.analysis,
                    ctx.state.learnings,
                )

            ctx.state.last_validation_grade = result.grade

            if result.is_valid:
                console.print(f"  [green]✓[/green] Validation passed (grade: {result.grade}/100)")
                return Services()

            console.print(f"  [yellow]![/yellow] Validation failed (grade: {result.grade}/100)")
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
            console.print(f"  [red]✗[/red] Validation error: {e}")
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
        console = ctx.state.console
        is_refine = ctx.state.compose_content is not None
        action = "Refining" if is_refine else "Generating"

        try:
            with console.status(f"[bold blue]{action} docker-compose.yaml..."):
                ctx.state.compose_content = await services.generate(
                    ctx.state.analysis,
                    ctx.state.dockerfile_content,
                    ctx.state.learnings,
                    ctx.state.hints,
                    existing=ctx.state.compose_content,
                    project_path=ctx.state.path,
                )

            settings = get_settings()
            compose_path = ctx.state.path / settings.cache_dir / "docker-compose.yaml"
            compose_path.parent.mkdir(parents=True, exist_ok=True)
            compose_path.write_text(ctx.state.compose_content)

            console.print(f"  [green]✓[/green] docker-compose.yaml {action.lower()[:-3]}ed")
            return Build()
        except ServicesError as e:
            console.print("  [red]✗[/red] Compose generation failed")
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
        console = ctx.state.console

        try:
            with console.status("[bold blue]Building Docker image..."):
                _, cache_hit = await docker.build(
                    ctx.state.path,
                    ctx.state.dockerfile_content,
                )
            if cache_hit:
                console.print("  [green]✓[/green] Docker image found in cache")
            else:
                console.print("  [green]✓[/green] Docker image built")
            return Start()
        except BuildError as e:
            console.print("  [red]✗[/red] Docker build failed")
            error_msg = str(e)
            # Extract last 15 lines of build output for context
            lines = error_msg.split("\n")
            if len(lines) > 15:
                error_msg = "\n".join(lines[-15:])
            learning = Learning(
                phase="build",
                error_type=type(e).__name__,
                error_message=error_msg,
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Start(BaseNode[ContainerizeState]):
    """Start containers with docker compose."""

    async def run(self, ctx: Ctx) -> Healthcheck | RetryOrHint:
        console = ctx.state.console

        try:
            with console.status("[bold blue]Starting containers..."):
                ctx.state.container_ids = await services.start(ctx.state.path)
            console.print(f"  [green]✓[/green] Started {len(ctx.state.container_ids)} container(s)")
            return Healthcheck()
        except StartError as e:
            console.print("  [red]✗[/red] Failed to start containers")
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
        console = ctx.state.console

        try:
            with console.status("[bold blue]Checking container health..."):
                await services.healthcheck(ctx.state.container_ids)
            console.print("  [green]✓[/green] All containers healthy")
            return End(Success())
        except HealthcheckError as e:
            console.print("  [red]✗[/red] Health check failed")
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
        console = ctx.state.console
        settings = get_settings()
        ctx.state.attempts_since_hint += 1

        if ctx.state.attempts_since_hint < settings.max_attempts:
            remaining = settings.max_attempts - ctx.state.attempts_since_hint
            console.print(f"  [dim]Retrying... ({remaining} attempts remaining)[/dim]")
            return Dockerfile()
        return HumanHint()


@dataclass
class HumanHint(BaseNode[ContainerizeState]):
    """Show errors and prompt user for hint."""

    async def run(self, ctx: Ctx) -> Dockerfile:
        console = ctx.state.console

        console.print("\n[red bold]Workflow needs help after multiple attempts[/red bold]\n")

        # Show last few errors (most recent first)
        recent_learnings = ctx.state.learnings[-3:]
        console.print("[yellow]Recent errors:[/yellow]")
        for learning in reversed(recent_learnings):
            console.print(f"  [bold]{learning.phase}[/bold]: {learning.error_type}")
            # Truncate long error messages
            msg = learning.error_message
            if len(msg) > 200:
                msg = msg[:200] + "..."
            console.print(f"    {msg}")
            if learning.context:
                console.print(f"    [dim]Hint: {learning.context[:100]}...[/dim]")

        console.print()
        hint = Prompt.ask("[cyan]Any hints to help fix this? (or 'q' to quit)[/cyan]")

        if hint.lower() == "q":
            raise KeyboardInterrupt()

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

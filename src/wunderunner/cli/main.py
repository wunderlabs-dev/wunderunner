"""Command-line interface for wunderunner."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.prompt import Prompt

from wunderunner.settings import get_settings
from wunderunner.workflows.containerize import Analyze, containerize_graph
from wunderunner.workflows.state import ContainerizeState, Learning, Severity


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging with Rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _configure_logfire() -> None:
    """Configure logfire if available and token is present."""
    settings = get_settings()
    if not settings.logfire_token:
        return

    try:
        import logfire

        logfire.configure(
            service_name="wunderunner",
            send_to_logfire="if-token-present",
        )
        logfire.instrument_pydantic_ai()
    except ImportError:
        pass


app = typer.Typer(
    name="wunderunner",
    help="AI-powered Docker configuration generator.",
)


def _validate_project_path(path: Path) -> Path:
    if not path.exists():
        raise typer.BadParameter(f"Path does not exist: {path}")
    if not path.is_dir():
        raise typer.BadParameter(f"Path is not a directory: {path}")
    return path.resolve()


def _make_progress_callback(console: Console):
    """Create a Rich-based progress callback."""
    severity_styles = {
        Severity.INFO: ("blue", ""),
        Severity.SUCCESS: ("green", "✓"),
        Severity.WARNING: ("yellow", "!"),
        Severity.ERROR: ("red", "✗"),
    }

    def callback(severity: Severity, message: str) -> None:
        color, icon = severity_styles[severity]
        if icon:
            console.print(f"  [{color}]{icon}[/{color}] {message}")
        else:
            console.print(f"  [{color}]•[/{color}] {message}")

    return callback


def _make_secret_prompt_callback(console: Console):
    """Create a Rich-based secret prompt callback."""

    def callback(name: str, service: str | None) -> str:
        service_hint = f" ({service})" if service else ""
        return Prompt.ask(
            f"  [bold]{name}[/bold]{service_hint}",
            password=True,
            console=console,
        )

    return callback


def _make_hint_prompt_callback(console: Console):
    """Create a Rich-based hint prompt callback."""

    def callback(learnings: list[Learning]) -> str | None:
        console.print("\n[yellow]Recent errors:[/yellow]")
        for learning in reversed(learnings):
            console.print(f"  [bold]{learning.phase}[/bold]: {learning.error_type}")
            msg = learning.error_message
            if len(msg) > 200:
                msg = msg[:200] + "..."
            console.print(f"    {msg}")
            if learning.context:
                console.print(f"    [dim]Hint: {learning.context[:100]}...[/dim]")

        console.print()
        hint = Prompt.ask(
            "[cyan]Any hints to help fix this? (or 'q' to quit)[/cyan]",
            console=console,
        )

        if hint.lower() == "q":
            return None
        return hint

    return callback


@app.command()
def init(
    project_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the project directory to containerize. Defaults to current directory.",
        ),
    ] = Path("."),
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Force rebuild from scratch, ignore cached analysis.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose logging.",
        ),
    ] = False,
) -> None:
    """Analyze a project and generate Docker configuration."""
    _setup_logging(verbose)
    _configure_logfire()
    project_path = _validate_project_path(project_path)
    console = Console()

    console.print(f"\n[bold]wunderunner[/bold] - containerizing {project_path.name}")
    if rebuild:
        console.print("[dim]  (ignoring cache)[/dim]")
    console.print()

    state = ContainerizeState(
        path=project_path,
        rebuild=rebuild,
        on_progress=_make_progress_callback(console),
        on_secret_prompt=_make_secret_prompt_callback(console),
        on_hint_prompt=_make_hint_prompt_callback(console),
    )

    try:
        asyncio.run(containerize_graph.run(Analyze(), state=state))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(130)

    console.print("\n[green bold]✓ Containerization complete![/green bold]")
    console.print("  [dim]Dockerfile and docker-compose.yaml written to project root[/dim]\n")


if __name__ == "__main__":
    app()

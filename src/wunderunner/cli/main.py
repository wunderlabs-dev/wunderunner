"""Command-line interface for wunderunner."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from wunderunner.workflows import ContainerizeContext, Failure, containerize

app = typer.Typer(
    name="wunderunner",
    help="AI-powered Docker configuration generator.",
)

console = Console()


def _validate_project_path(path: Path) -> Path:
    if not path.exists():
        raise typer.BadParameter(f"Path does not exist: {path}")
    if not path.is_dir():
        raise typer.BadParameter(f"Path is not a directory: {path}")
    return path.resolve()


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
) -> None:
    """Analyze a project and generate Docker configuration."""
    project_path = _validate_project_path(project_path)

    console.print(f"[bold]Analyzing project:[/bold] {project_path}")
    if rebuild:
        console.print("[dim]Cache:[/dim] Ignoring cached analysis (--rebuild)")

    ctx = ContainerizeContext(path=project_path, rebuild=rebuild)
    try:
        asyncio.run(containerize(ctx))
    except Failure:
        console.print("\n[red]✗ Containerization failed after max attempts[/red]")
        sys.exit(1)

    console.print("\n[green]✓ Containerization complete[/green]")


if __name__ == "__main__":
    app()

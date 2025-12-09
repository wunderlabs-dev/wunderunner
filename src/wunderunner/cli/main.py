"""Command-line interface for wunderunner."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from wunderunner.workflows.containerize import Analyze, containerize_graph
from wunderunner.workflows.state import ContainerizeState

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
    console = Console()

    console.print(f"\n[bold]wunderunner[/bold] - containerizing {project_path.name}")
    if rebuild:
        console.print("[dim]  (ignoring cache)[/dim]")
    console.print()

    state = ContainerizeState(path=project_path, rebuild=rebuild, console=console)

    try:
        asyncio.run(containerize_graph.run(Analyze(), state=state))
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(130)

    console.print("\n[green bold]✓ Containerization complete![/green bold]")
    console.print(f"  [dim]Files written to {project_path / '.wunderunner'}[/dim]\n")


if __name__ == "__main__":
    app()

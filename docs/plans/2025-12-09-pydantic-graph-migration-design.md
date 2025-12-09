# Pydantic Graph Migration Design

## Overview

Migrate the containerize workflow from a simple retry loop to Pydantic Graph to enable:

1. **Human-in-the-loop** - CLI prompts for secrets/config and hints after failures
2. **Persistence** - Resume long-running jobs after crash or Ctrl+C
3. **Visualization** - Mermaid diagrams for debugging and documentation
4. **Iterative refinement** - Agents refine existing artifacts rather than regenerating

## Current State

The workflow is a linear sequence with retry logic in `workflows/containerize.py`:

```
Analyze → Dockerfile → Services → Build → Start → Healthcheck
    ↓ (on failure)
  Retry N times → Fail
```

Limitations:
- No human intervention possible
- No persistence (crash = start over)
- Artifacts regenerated from scratch on each retry

## Target Architecture

### Graph Structure

```
┌─────────┐
│ Analyze │
└────┬────┘
     │
     ▼
┌─────────────────┐
│ CollectSecrets? │ ─── (no secrets) ───┐
└────────┬────────┘                     │
         │ (has secrets)                │
         ▼                              │
┌─────────────────┐                     │
│ CollectSecrets  │                     │
└────────┬────────┘                     │
         │                              │
         ▼                              ▼
     ┌────────────┐
     │ Dockerfile │ ◄──────────────────────────────┐
     └─────┬──────┘                                │
           │                                       │
           ▼                                       │
     ┌──────────┐                                  │
     │ Services │                                  │
     └─────┬────┘                                  │
           │                                       │
           ▼                                       │
     ┌─────────┐                                   │
     │  Build  │                                   │
     └────┬────┘                                   │
          │                                        │
          ▼                                        │
     ┌─────────┐                                   │
     │  Start  │                                   │
     └────┬────┘                                   │
          │                                        │
          ▼                                        │
   ┌─────────────┐                                 │
   │ Healthcheck │                                 │
   └──────┬──────┘                                 │
          │                                        │
    ┌─────┴─────┐                                  │
    ▼           ▼                                  │
End[Success]  RetryOrHint ◄── (any failure) ──────┤
                  │                                │
          ┌───────┴───────┐                        │
          ▼               ▼                        │
    (attempts < N)   (attempts >= N)               │
          │               │                        │
          │         ┌─────┴─────┐                  │
          │         │ HumanHint │                  │
          │         └─────┬─────┘                  │
          │               │                        │
          └───────────────┴────────────────────────┘
                          │
                          ▼
                      Dockerfile (iterates on existing)
```

### Retry Flow

1. Any node failure → `RetryOrHint` node
2. If `attempts_since_hint < max_attempts` → Auto-retry from `Dockerfile`
3. If `attempts_since_hint >= max_attempts` → `HumanHint` node prompts user
4. After hint → Reset counter, retry from `Dockerfile`
5. Repeat until success or user quits (Ctrl+C)

### Iterative Refinement

All generation activities support iteration:
- If artifact exists in state → Agent refines it with error context
- If artifact doesn't exist → Agent generates fresh

This means retries don't discard previous work - they build on it.

## File Structure

```
src/wunderunner/
├── workflows/
│   ├── __init__.py
│   ├── containerize.py      # Graph definition + nodes (replaces current)
│   └── state.py             # ContainerizeState dataclass (new)
├── activities/              # Unchanged - nodes call these
│   ├── project.py
│   ├── dockerfile.py        # Add existing param for refinement
│   ├── services.py          # Add existing param for refinement
│   └── docker.py
└── models/                  # Unchanged
```

Files to delete:
- `workflows/base.py` - Replaced by `state.py`
- `workflows/run.py` - Replaced by graph execution

## State Model

```python
# workflows/state.py

from dataclasses import dataclass, field
from pathlib import Path

from wunderunner.models.analysis import Analysis


@dataclass
class Learning:
    """Captured learning from a failed phase."""
    phase: str
    error_type: str
    error_message: str
    context: str | None = None


@dataclass
class ContainerizeState:
    """Shared state for containerize workflow."""

    path: Path
    rebuild: bool = False

    # Analysis result (set by Analyze node)
    analysis: Analysis | None = None

    # Secret values collected from user (name -> value)
    secret_values: dict[str, str] = field(default_factory=dict)

    # Accumulated learnings and hints
    learnings: list[Learning] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    # Retry tracking (reset after human hint)
    attempts_since_hint: int = 0

    # Intermediate artifacts (for persistence and refinement)
    dockerfile_content: str | None = None
    compose_content: str | None = None
    container_ids: list[str] = field(default_factory=list)
```

## Node Definitions

```python
# workflows/containerize.py

from dataclasses import dataclass
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from wunderunner.workflows.state import ContainerizeState, Learning

Ctx = GraphRunContext[ContainerizeState, None]


@dataclass
class Analyze(BaseNode[ContainerizeState]):
    """Run analysis agents and check for secrets."""

    async def run(self, ctx: Ctx) -> "CollectSecrets | Dockerfile":
        analysis = await project.analyze(ctx.state.path, ctx.state.rebuild)
        ctx.state.analysis = analysis

        secrets = [v for v in analysis.env_vars if v.secret]
        if secrets:
            return CollectSecrets()
        return Dockerfile()


@dataclass
class CollectSecrets(BaseNode[ContainerizeState]):
    """Prompt user for secret values via CLI."""

    async def run(self, ctx: Ctx) -> "Dockerfile":
        secrets = [v for v in ctx.state.analysis.env_vars if v.secret]
        for var in secrets:
            value = Prompt.ask(
                f"Enter value for [bold]{var.name}[/bold]",
                password=True
            )
            ctx.state.secret_values[var.name] = value
        return Dockerfile()


@dataclass
class Dockerfile(BaseNode[ContainerizeState]):
    """Generate or refine Dockerfile."""

    async def run(self, ctx: Ctx) -> "Services | RetryOrHint":
        try:
            ctx.state.dockerfile_content = await dockerfile.generate(
                ctx.state.analysis,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.dockerfile_content,
            )
            return Services()
        except DockerfileError as e:
            learning = Learning(
                phase="dockerfile",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            ctx.state.learnings.append(learning)
            return RetryOrHint(learning=learning)


@dataclass
class Services(BaseNode[ContainerizeState]):
    """Generate or refine docker-compose.yaml."""

    async def run(self, ctx: Ctx) -> "Build | RetryOrHint":
        try:
            ctx.state.compose_content = await services.generate(
                ctx.state.analysis,
                ctx.state.dockerfile_content,
                ctx.state.learnings,
                ctx.state.hints,
                existing=ctx.state.compose_content,
            )
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

    async def run(self, ctx: Ctx) -> "Start | RetryOrHint":
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

    async def run(self, ctx: Ctx) -> "Healthcheck | RetryOrHint":
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

    async def run(self, ctx: Ctx) -> "End[Success] | RetryOrHint":
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

    async def run(self, ctx: Ctx) -> "Dockerfile | HumanHint":
        settings = get_settings()
        ctx.state.attempts_since_hint += 1

        if ctx.state.attempts_since_hint < settings.max_attempts:
            return Dockerfile()
        return HumanHint()


@dataclass
class HumanHint(BaseNode[ContainerizeState]):
    """Show errors and prompt user for hint."""

    async def run(self, ctx: Ctx) -> "Dockerfile":
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


@dataclass
class Success:
    """Workflow completed successfully."""
    pass


# Graph definition
containerize_graph = Graph(
    nodes=[
        Analyze,
        CollectSecrets,
        Dockerfile,
        Services,
        Build,
        Start,
        Healthcheck,
        RetryOrHint,
        HumanHint,
    ],
    state_type=ContainerizeState,
    end_type=Success,
)
```

## Activity Changes

### dockerfile.py

```python
async def generate(
    analysis: Analysis,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
) -> str:
    """Generate or refine Dockerfile.

    Args:
        analysis: Project analysis result.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this Dockerfile instead of generating fresh.

    Returns:
        Dockerfile content.

    Raises:
        DockerfileError: If generation/refinement fails.
    """
    ...
```

### services.py

```python
async def generate(
    analysis: Analysis,
    dockerfile_content: str,
    learnings: list[Learning],
    hints: list[str],
    existing: str | None = None,
) -> str:
    """Generate or refine docker-compose.yaml.

    Args:
        analysis: Project analysis result.
        dockerfile_content: The Dockerfile being used.
        learnings: Errors from previous attempts.
        hints: User-provided hints.
        existing: If provided, refine this compose file instead of generating fresh.

    Returns:
        docker-compose.yaml content.

    Raises:
        ServicesError: If generation/refinement fails.
    """
    ...
```

## CLI Integration

```python
# cli/main.py

from pydantic_graph import FileStatePersistence

@app.command()
async def containerize(path: Path, rebuild: bool = False, resume: bool = False):
    """Containerize a project."""

    persistence = FileStatePersistence(path / ".wunderunner" / "workflow.json")

    if resume:
        # Resume from saved state
        async with containerize_graph.iter_from_persistence(persistence) as run:
            async for node in run:
                pass  # Graph handles execution
        result = run.result
    else:
        # Fresh run
        state = ContainerizeState(path=path, rebuild=rebuild)
        result = await containerize_graph.run(
            Analyze(),
            state=state,
            persistence=persistence,
        )

    console.print("[green]Success![/green]")
```

## Visualization

Generate Mermaid diagram for documentation:

```python
# Generate and save diagram
containerize_graph.mermaid_save("docs/workflow.png")

# Or get mermaid code for embedding
mermaid_code = containerize_graph.mermaid_code()
```

## Implementation Tasks

1. Add `pydantic-graph` dependency to `pyproject.toml`
2. Create `workflows/state.py` with `Learning` and `ContainerizeState`
3. Rewrite `workflows/containerize.py` with graph nodes
4. Update `activities/dockerfile.py` signature (add `existing` param)
5. Update `activities/services.py` signature (add `existing` param)
6. Update `cli/main.py` to use graph execution with persistence
7. Delete `workflows/base.py` and `workflows/run.py`
8. Add tests for graph execution and state transitions
9. Generate and commit workflow diagram

## Dependencies

```toml
# pyproject.toml
dependencies = [
    "pydantic-ai",      # Already have this
    "pydantic-graph",   # Add this (or it may come with pydantic-ai)
]
```

## Open Questions

None - design is complete and approved.

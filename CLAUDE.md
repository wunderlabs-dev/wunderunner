# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**wunderunner** (`wxr`) is an AI-assisted CLI that analyzes projects, generates Dockerfile + docker-compose.yaml, builds/runs containers, and learns from runtime errors. Uses Pydantic AI agents with filesystem tools to analyze codebases and generate container configurations.

## Development Commands

```bash
make install      # Install dependencies with uv sync
make dev          # Install with all extras
make test         # Run pytest tests
make lint         # Run ruff linter
make format       # Format with ruff
make clean        # Remove build artifacts and caches
```

Single test: `uv run pytest tests/test_foo.py::test_specific -v`

## Architecture

```
src/wunderunner/
├── cli/              # Typer CLI (main.py -> `wxr` command)
├── settings.py       # API key config, model selection (pydantic-settings)
└── __init__.py
```

**Planned structure (not yet implemented):**
```
├── agents/           # Pydantic AI agents
│   ├── common.py     # AgentDeps, base agent setup
│   ├── analysis.py   # Project analysis agent
│   ├── dockerfile.py # Dockerfile generation agent
│   ├── compose.py    # docker-compose generation agent
│   ├── validation.py # Validation/grading agent
│   └── tools/        # Agent tools (filesystem.py: read_file, list_dir, search_files)
├── models/           # Pydantic v2 data models
├── storage/          # Per-project YAML storage (.wunderunner/)
├── runtime/          # Container orchestration (Docker API, log watcher)
├── prompts/          # Jinja2 prompt templates (.j2)
└── templates/        # Generation templates (Dockerfiles, compose, scripts)
```

## Key Design Decisions

- **AI Framework:** Pydantic AI (multi-provider, structured output, tool support)
- **Model Selection:** Auto-detect from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars
- **CLI:** Typer with Rich for output
- **Prompts:** Jinja2 templates in `prompts/` directory
- **Storage:** YAML files in `.wunderunner/` per analyzed project

## Python Best Practices

**Target:** Python 3.11+ with strict mypy

### Core Principles (Non-Negotiable)

1. **Functions over classes.** Use classes only when you need state that persists across multiple method calls. Default to plain functions.
2. **No nested blocks.** If you have nested if/for/try blocks, split into separate functions. Flat is better than nested.
3. **No nested try/except.** One try/except per function max. If you need more, refactor.
4. **Simple flows.** If a function is hard to follow, it's doing too much. Break it up.

### Type Hints
- All functions and methods require complete type hints
- Use `|` union syntax (3.10+): `str | None` not `Optional[str]`
- Use `list[str]` not `List[str]` (built-in generics)
- Use `Self` for return type in methods returning own class

### Data Structures
- **Pydantic models** for external data (API, files, user input)
- **dataclasses** for internal data structures
- **TypedDict** for dict shapes when Pydantic is overkill

### Async Patterns
- Use `async/await` for all I/O operations (file reads, Docker API, HTTP)
- `asyncio.gather()` for concurrent independent operations
- `asyncio.TaskGroup` (3.11+) for structured concurrency with error handling

### Code Style
- Early returns to reduce nesting
- Comprehensions over explicit loops when readable
- Context managers (`async with`) for resource handling
- `functools.partial` and `functools.lru_cache` where appropriate

### Error Handling
- Custom exception hierarchy under `wunderunner.exceptions`
- Specific exceptions, not generic `Exception`
- Let unexpected errors propagate (don't catch-and-log-and-continue)

### Testing
- pytest with `pytest-asyncio` for async tests
- Fixtures in `conftest.py`, not test files
- Test behavior, not implementation
- Never mock what you don't own; use fakes for external services

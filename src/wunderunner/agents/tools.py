"""Filesystem tools for analysis agents."""

import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic_ai import Agent, RunContext


@dataclass(slots=True)
class AgentDeps:
    """Dependencies injected into agent tools."""

    project_dir: Path
    max_file_size: int = 50_000


def _validate_path(deps: AgentDeps, relative_path: str) -> Path:
    """Resolve and validate path is within project directory."""
    full_path = (deps.project_dir / relative_path).resolve()
    if not full_path.is_relative_to(deps.project_dir.resolve()):
        raise ValueError(f"Path escapes project directory: {relative_path}")
    return full_path


async def read_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """Read file contents. Returns truncated content if file exceeds max size."""
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: File not found: {path}"
    if not full_path.is_file():
        return f"Error: Not a file: {path}"

    content = full_path.read_text(errors="replace")
    if len(content) > ctx.deps.max_file_size:
        return content[: ctx.deps.max_file_size] + f"\n... (truncated, {len(content)} bytes total)"
    return content


async def list_dir(ctx: RunContext[AgentDeps], path: str = ".") -> str:
    """List directory contents. Directories are suffixed with /."""
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: Directory not found: {path}"
    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    entries = []
    for entry in sorted(full_path.iterdir()):
        name = entry.name
        if entry.is_dir():
            name += "/"
        entries.append(name)
    return "\n".join(entries)


async def glob(ctx: RunContext[AgentDeps], pattern: str) -> str:
    """Find files matching glob pattern. Returns up to 100 matches."""
    project_dir = ctx.deps.project_dir.resolve()
    matches = []

    for path in project_dir.rglob("*"):
        if path.is_file() and fnmatch.fnmatch(path.name, pattern):
            relative = path.relative_to(project_dir)
            matches.append(str(relative))
            if len(matches) >= 100:
                break

    if not matches:
        return f"No files matching: {pattern}"
    return "\n".join(sorted(matches))


async def grep(ctx: RunContext[AgentDeps], pattern: str, path: str = ".") -> str:
    """Search file contents for regex pattern. Returns file:line:content format."""
    full_path = _validate_path(ctx.deps, path)

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Error: Invalid regex: {e}"

    results = []
    max_results = 100

    if full_path.is_file():
        files = [full_path]
    elif full_path.is_dir():
        files = [f for f in full_path.rglob("*") if f.is_file()]
    else:
        return f"Error: Path not found: {path}"

    for file_path in files:
        if len(results) >= max_results:
            break

        try:
            content = file_path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        relative = file_path.relative_to(ctx.deps.project_dir.resolve())
        for line_num, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                results.append(f"{relative}:{line_num}:{line.strip()}")
                if len(results) >= max_results:
                    break

    if not results:
        return f"No matches for: {pattern}"
    return "\n".join(results)


async def file_stats(ctx: RunContext[AgentDeps], path: str) -> str:
    """Get file metadata: size and modification time."""
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: File not found: {path}"

    stat = full_path.stat()
    size = stat.st_size
    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return f"size: {size} bytes\nmodified: {mtime}"


def register_tools(agent: Agent[AgentDeps, object]) -> None:
    """Register all filesystem tools on an agent."""
    agent.tool(read_file)
    agent.tool(list_dir)
    agent.tool(glob)
    agent.tool(grep)
    agent.tool(file_stats)

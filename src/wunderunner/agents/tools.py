"""Filesystem tools for analysis agents."""

import asyncio
import fnmatch
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic_ai import Agent, RunContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentDeps:
    """Dependencies injected into agent tools."""

    project_dir: Path
    max_file_size: int = 15_000  # ~15KB, roughly 3-4K tokens


# Directories to skip during recursive file operations
SKIP_DIRS = frozenset({
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    "coverage",
    ".turbo",
    ".cache",
})

# File extensions to skip (binary/generated)
SKIP_EXTENSIONS = frozenset({
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".lock",  # lock files are huge
    ".min.js",
    ".min.css",
    ".map",
    ".wasm",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
})


def _validate_path(deps: AgentDeps, relative_path: str) -> Path:
    """Resolve and validate path is within project directory."""
    full_path = (deps.project_dir / relative_path).resolve()
    if not full_path.is_relative_to(deps.project_dir.resolve()):
        raise ValueError(f"Path escapes project directory: {relative_path}")
    return full_path


def _iter_files(root: Path, max_files: int = 5000) -> list[Path]:
    """Iterate files, skipping heavy directories and binary files."""
    files = []
    count = 0

    def walk(directory: Path) -> None:
        nonlocal count
        if count >= max_files:
            return

        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if count >= max_files:
                return

            if entry.is_dir() and entry.name not in SKIP_DIRS:
                walk(entry)
            elif entry.is_file() and entry.suffix.lower() not in SKIP_EXTENSIONS:
                files.append(entry)
                count += 1

    walk(root)
    return files


async def read_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """Read file contents. Returns truncated content if file exceeds max size."""
    logger.debug("tool:read_file(%s)", path)
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: File not found: {path}"
    if not full_path.is_file():
        return f"Error: Not a file: {path}"

    content = await asyncio.to_thread(full_path.read_text, errors="replace")
    if len(content) > ctx.deps.max_file_size:
        return content[: ctx.deps.max_file_size] + f"\n... (truncated, {len(content)} bytes total)"
    return content


def _list_dir_sync(full_path: Path) -> list[str]:
    """Synchronous list_dir for thread pool."""
    entries = []
    for entry in sorted(full_path.iterdir()):
        name = entry.name
        if entry.is_dir():
            name += "/"
        entries.append(name)
    return entries


async def list_dir(ctx: RunContext[AgentDeps], path: str = ".") -> str:
    """List directory contents. Directories are suffixed with /."""
    logger.debug("tool:list_dir(%s)", path)
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: Directory not found: {path}"
    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    entries = await asyncio.to_thread(_list_dir_sync, full_path)
    return "\n".join(entries)


def _glob_sync(pattern: str, project_dir: Path) -> list[str]:
    """Synchronous glob for thread pool."""
    files = _iter_files(project_dir)
    matches = []

    for file_path in files:
        if fnmatch.fnmatch(file_path.name, pattern):
            relative = file_path.relative_to(project_dir)
            matches.append(str(relative))
            if len(matches) >= 100:
                break

    return sorted(matches)


async def glob(ctx: RunContext[AgentDeps], pattern: str) -> str:
    """Find files matching glob pattern. Returns up to 100 matches."""
    logger.debug("tool:glob(%s)", pattern)
    project_dir = ctx.deps.project_dir.resolve()

    matches = await asyncio.to_thread(_glob_sync, pattern, project_dir)

    if not matches:
        return f"No files matching: {pattern}"
    return "\n".join(matches)


def _grep_sync(
    pattern: re.Pattern, files: list[Path], project_dir: Path, max_results: int = 50
) -> list[str]:
    """Synchronous grep implementation for thread pool."""
    results = []

    for file_path in files:
        if len(results) >= max_results:
            break

        try:
            content = file_path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        relative = file_path.relative_to(project_dir)
        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                # Truncate long lines
                line_text = line.strip()
                if len(line_text) > 200:
                    line_text = line_text[:200] + "..."
                results.append(f"{relative}:{line_num}:{line_text}")
                if len(results) >= max_results:
                    break

    return results


async def grep(ctx: RunContext[AgentDeps], pattern: str, path: str = ".") -> str:
    """Search file contents for regex pattern. Returns file:line:content format."""
    logger.debug("tool:grep(%s, %s)", pattern, path)
    full_path = _validate_path(ctx.deps, path)

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Error: Invalid regex: {e}"

    if full_path.is_file():
        files = [full_path]
    elif full_path.is_dir():
        files = _iter_files(full_path)
    else:
        return f"Error: Path not found: {path}"

    project_dir = ctx.deps.project_dir.resolve()
    results = await asyncio.to_thread(_grep_sync, regex, files, project_dir)

    if not results:
        return f"No matches for: {pattern}"
    return "\n".join(results)


async def file_stats(ctx: RunContext[AgentDeps], path: str) -> str:
    """Get file metadata: size and modification time."""
    logger.debug("tool:file_stats(%s)", path)
    full_path = _validate_path(ctx.deps, path)
    if not full_path.exists():
        return f"Error: File not found: {path}"

    stat = await asyncio.to_thread(full_path.stat)
    size = stat.st_size
    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return f"size: {size} bytes\nmodified: {mtime}"


# Sensitive file patterns that should not be overwritten
SENSITIVE_PATTERNS = frozenset({".env", "credentials", "secret", ".key", ".pem"})


def _write_file_sync(full_path: Path, content: str) -> str:
    """Synchronous write for thread pool."""
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return f"Successfully wrote {len(content)} bytes to {full_path.name}"


async def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """Write content to a file in the project directory."""
    logger.debug("tool:write_file(%s)", path)
    full_path = _validate_path(ctx.deps, path)

    # Don't overwrite existing sensitive files
    is_sensitive = any(p in path.lower() for p in SENSITIVE_PATTERNS)
    if is_sensitive and full_path.exists():
        return f"Error: Refusing to overwrite sensitive file: {path}"

    try:
        return await asyncio.to_thread(_write_file_sync, full_path, content)
    except OSError as e:
        return f"Error writing file: {e}"


async def edit_file(
    ctx: RunContext[AgentDeps],
    path: str,
    old_string: str,
    new_string: str,
) -> str:
    """Replace old_string with new_string in a file.

    The old_string must match exactly (including whitespace/indentation).
    Use this for surgical edits instead of rewriting entire files.
    """
    logger.debug("tool:edit_file(%s)", path)
    full_path = _validate_path(ctx.deps, path)

    if not full_path.exists():
        return f"Error: File not found: {path}"

    # Don't edit sensitive files
    is_sensitive = any(p in path.lower() for p in SENSITIVE_PATTERNS)
    if is_sensitive:
        return f"Error: Refusing to edit sensitive file: {path}"

    content = await asyncio.to_thread(full_path.read_text, errors="replace")

    if old_string not in content:
        return f"Error: old_string not found in {path}"

    count = content.count(old_string)
    if count > 1:
        return f"Error: old_string appears {count} times in {path}. Make it more specific."

    new_content = content.replace(old_string, new_string, 1)

    try:
        await asyncio.to_thread(full_path.write_text, new_content)
        return f"Successfully edited {path}"
    except OSError as e:
        return f"Error writing file: {e}"


def register_tools(agent: Agent[AgentDeps, object], include_write: bool = False) -> None:
    """Register filesystem tools on an agent."""
    agent.tool(read_file)
    agent.tool(list_dir)
    agent.tool(glob)
    agent.tool(grep)
    agent.tool(file_stats)
    if include_write:
        agent.tool(write_file)
        agent.tool(edit_file)

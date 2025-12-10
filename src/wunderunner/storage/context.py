"""Project context persistence."""

import logging
from pathlib import Path

import aiofiles
from pydantic import ValidationError

from wunderunner.agents.context import summarize
from wunderunner.models.context import ContextEntry, ProjectContext
from wunderunner.settings import get_settings

logger = logging.getLogger(__name__)

CONTEXT_FILE = "context.json"
SUMMARIZATION_THRESHOLD = 10


def _get_context_path(project_path: Path) -> Path:
    """Get the path to the context file."""
    settings = get_settings()
    return project_path / settings.cache_dir / CONTEXT_FILE


async def load_context(project_path: Path) -> ProjectContext:
    """Load project context from disk. Returns empty context if not found."""
    context_path = _get_context_path(project_path)

    if not context_path.exists():
        return ProjectContext()

    try:
        async with aiofiles.open(context_path) as f:
            content = await f.read()
        return ProjectContext.model_validate_json(content)
    except (ValidationError, OSError, ValueError) as e:
        logger.warning("Failed to load context from %s: %s", context_path, e)
        return ProjectContext()


async def save_context(project_path: Path, context: ProjectContext) -> None:
    """Save project context to disk."""
    context_path = _get_context_path(project_path)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(context_path, "w") as f:
        await f.write(context.model_dump_json(indent=2))


async def add_entry(project_path: Path, entry: ContextEntry) -> ProjectContext:
    """Add an entry to project context, summarize if needed, and save.

    Triggers summarization when entries_since_summary reaches threshold.

    Returns:
        Updated context.
    """
    context = await load_context(project_path)
    context.add_entry(entry)

    if context.needs_summarization(SUMMARIZATION_THRESHOLD):
        summary = await summarize(context.entries, context.summary)
        context.apply_summary(summary)

    await save_context(project_path, context)
    return context

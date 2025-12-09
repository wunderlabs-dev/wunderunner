"""Project context persistence."""

from pathlib import Path

from wunderunner.agents.context import summarize
from wunderunner.models.context import ContextEntry, ProjectContext
from wunderunner.settings import get_settings

CONTEXT_FILE = "context.json"
SUMMARIZATION_THRESHOLD = 10


def _get_context_path(project_path: Path) -> Path:
    """Get the path to the context file."""
    settings = get_settings()
    return project_path / settings.cache_dir / CONTEXT_FILE


def load_context(project_path: Path) -> ProjectContext:
    """Load project context from disk. Returns empty context if not found."""
    context_path = _get_context_path(project_path)

    if not context_path.exists():
        return ProjectContext()

    try:
        return ProjectContext.model_validate_json(context_path.read_text())
    except Exception:
        return ProjectContext()


def save_context(project_path: Path, context: ProjectContext) -> None:
    """Save project context to disk."""
    context_path = _get_context_path(project_path)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(context.model_dump_json(indent=2))


async def add_entry(project_path: Path, entry: ContextEntry) -> ProjectContext:
    """Add an entry to project context, summarize if needed, and save.

    Triggers summarization when entries_since_summary reaches threshold.

    Returns:
        Updated context.
    """
    context = load_context(project_path)
    context.add_entry(entry)

    if context.needs_summarization(SUMMARIZATION_THRESHOLD):
        summary = await summarize(context.entries, context.summary)
        context.apply_summary(summary)

    save_context(project_path, context)
    return context

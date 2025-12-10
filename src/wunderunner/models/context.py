"""Pydantic models for project context persistence."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class EntryType(str, Enum):
    """Type of context entry."""

    DOCKERFILE = "dockerfile"
    BUILD = "build"
    VALIDATION = "validation"
    HEALTHCHECK = "healthcheck"


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


class ContextEntry(BaseModel):
    """A single learning entry in the project context."""

    entry_type: EntryType
    error: str | None = Field(default=None, description="Error message if this was a failure")
    fix: str | None = Field(default=None, description="What was done to fix it")
    explanation: str = Field(description="Why this matters for future iterations")
    created_at: datetime = Field(default_factory=_utc_now)


class ProjectContext(BaseModel):
    """Persistent learning context for a project.

    Stores historical fixes and learnings to prevent regressions
    and improve future Dockerfile generation.
    """

    entries: list[ContextEntry] = Field(
        default_factory=list,
        description="Recent entries, most recent first.",
    )
    violation_count: int = Field(
        default=0,
        description="Number of times a regression was detected",
    )
    summary: str | None = Field(
        default=None,
        description="AI-generated summary of past learnings",
    )
    entries_since_summary: int = Field(
        default=0,
        description="Number of entries added since last summarization",
    )

    def add_entry(self, entry: ContextEntry) -> None:
        """Add entry to front and increment counter."""
        self.entries.insert(0, entry)
        self.entries_since_summary += 1

    def needs_summarization(self, threshold: int = 10) -> bool:
        """Check if we have enough entries to trigger summarization."""
        return self.entries_since_summary >= threshold

    def apply_summary(self, summary: str) -> None:
        """Apply summary and clear entries."""
        self.summary = summary
        self.entries = []
        self.entries_since_summary = 0

    def get_dockerfile_fixes(self) -> list[ContextEntry]:
        """Get only dockerfile-related entries for regression checking."""
        return [e for e in self.entries if e.entry_type in (EntryType.DOCKERFILE, EntryType.BUILD)]

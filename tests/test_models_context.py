"""Tests for context models."""

from datetime import UTC, datetime

import pytest

from wunderunner.models.context import (
    ContextEntry,
    EntryType,
    ProjectContext,
    _utc_now,
)


class TestUtcNow:
    """Test _utc_now helper."""

    def test_returns_utc_datetime(self):
        """_utc_now returns UTC datetime."""
        now = _utc_now()
        assert now.tzinfo == UTC

    def test_returns_current_time(self):
        """_utc_now returns approximately current time."""
        before = datetime.now(UTC)
        now = _utc_now()
        after = datetime.now(UTC)
        assert before <= now <= after


class TestEntryType:
    """Test EntryType enum."""

    def test_entry_types_exist(self):
        """All expected entry types exist."""
        assert EntryType.DOCKERFILE == "dockerfile"
        assert EntryType.BUILD == "build"
        assert EntryType.VALIDATION == "validation"
        assert EntryType.HEALTHCHECK == "healthcheck"


class TestContextEntry:
    """Test ContextEntry model."""

    def test_minimal_entry(self):
        """ContextEntry with required fields only."""
        entry = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            explanation="Test explanation",
        )
        assert entry.entry_type == EntryType.DOCKERFILE
        assert entry.explanation == "Test explanation"
        assert entry.error is None
        assert entry.fix is None
        assert entry.created_at is not None

    def test_full_entry(self):
        """ContextEntry with all fields."""
        entry = ContextEntry(
            entry_type=EntryType.BUILD,
            error="npm ERR! Missing script",
            fix="Added build script to package.json",
            explanation="package.json was missing build script",
        )
        assert entry.error == "npm ERR! Missing script"
        assert entry.fix == "Added build script to package.json"

    def test_created_at_default(self):
        """created_at defaults to current UTC time."""
        before = datetime.now(UTC)
        entry = ContextEntry(
            entry_type=EntryType.VALIDATION,
            explanation="test",
        )
        after = datetime.now(UTC)
        assert before <= entry.created_at <= after


class TestProjectContext:
    """Test ProjectContext model."""

    def test_empty_context(self):
        """ProjectContext defaults to empty state."""
        ctx = ProjectContext()
        assert ctx.entries == []
        assert ctx.violation_count == 0
        assert ctx.summary is None
        assert ctx.entries_since_summary == 0

    def test_add_entry_inserts_at_front(self):
        """add_entry inserts new entry at front of list."""
        ctx = ProjectContext()
        entry1 = ContextEntry(entry_type=EntryType.BUILD, explanation="first")
        entry2 = ContextEntry(entry_type=EntryType.BUILD, explanation="second")

        ctx.add_entry(entry1)
        ctx.add_entry(entry2)

        assert len(ctx.entries) == 2
        assert ctx.entries[0].explanation == "second"  # Most recent first
        assert ctx.entries[1].explanation == "first"

    def test_add_entry_increments_counter(self):
        """add_entry increments entries_since_summary."""
        ctx = ProjectContext()
        assert ctx.entries_since_summary == 0

        entry = ContextEntry(entry_type=EntryType.BUILD, explanation="test")
        ctx.add_entry(entry)
        assert ctx.entries_since_summary == 1

        ctx.add_entry(entry)
        assert ctx.entries_since_summary == 2

    def test_needs_summarization_below_threshold(self):
        """needs_summarization returns False below threshold."""
        ctx = ProjectContext(entries_since_summary=5)
        assert ctx.needs_summarization(threshold=10) is False

    def test_needs_summarization_at_threshold(self):
        """needs_summarization returns True at threshold."""
        ctx = ProjectContext(entries_since_summary=10)
        assert ctx.needs_summarization(threshold=10) is True

    def test_needs_summarization_above_threshold(self):
        """needs_summarization returns True above threshold."""
        ctx = ProjectContext(entries_since_summary=15)
        assert ctx.needs_summarization(threshold=10) is True

    def test_apply_summary_clears_entries(self):
        """apply_summary sets summary and clears entries."""
        entry = ContextEntry(entry_type=EntryType.BUILD, explanation="test")
        ctx = ProjectContext(entries=[entry], entries_since_summary=5)

        ctx.apply_summary("Summary of learnings")

        assert ctx.summary == "Summary of learnings"
        assert ctx.entries == []
        assert ctx.entries_since_summary == 0

    def test_get_dockerfile_fixes_filters_correctly(self):
        """get_dockerfile_fixes returns only dockerfile and build entries."""
        dockerfile_entry = ContextEntry(entry_type=EntryType.DOCKERFILE, explanation="df")
        build_entry = ContextEntry(entry_type=EntryType.BUILD, explanation="build")
        validation_entry = ContextEntry(entry_type=EntryType.VALIDATION, explanation="val")
        healthcheck_entry = ContextEntry(entry_type=EntryType.HEALTHCHECK, explanation="hc")

        ctx = ProjectContext(
            entries=[dockerfile_entry, build_entry, validation_entry, healthcheck_entry]
        )

        fixes = ctx.get_dockerfile_fixes()
        assert len(fixes) == 2
        assert dockerfile_entry in fixes
        assert build_entry in fixes
        assert validation_entry not in fixes
        assert healthcheck_entry not in fixes

    def test_serialization_roundtrip(self):
        """ProjectContext serializes and deserializes correctly."""
        entry = ContextEntry(
            entry_type=EntryType.DOCKERFILE,
            error="test error",
            fix="test fix",
            explanation="test explanation",
        )
        ctx = ProjectContext(
            entries=[entry],
            violation_count=2,
            summary="Test summary",
            entries_since_summary=1,
        )

        json_str = ctx.model_dump_json()
        restored = ProjectContext.model_validate_json(json_str)

        assert restored.violation_count == 2
        assert restored.summary == "Test summary"
        assert restored.entries_since_summary == 1
        assert len(restored.entries) == 1
        assert restored.entries[0].error == "test error"

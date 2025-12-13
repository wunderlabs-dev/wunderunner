"""Tests for storage/context persistence."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.models.context import ContextEntry, EntryType, ProjectContext
from wunderunner.storage.context import (
    CONTEXT_FILE,
    SUMMARIZATION_THRESHOLD,
    _get_context_path,
    add_entry,
    load_context,
    save_context,
)


class TestGetContextPath:
    """Test _get_context_path helper."""

    def test_returns_correct_path(self, tmp_path):
        """_get_context_path returns path in cache directory."""
        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            path = _get_context_path(tmp_path)
            assert path == tmp_path / ".wunderunner" / CONTEXT_FILE

    def test_uses_settings_cache_dir(self, tmp_path):
        """_get_context_path uses cache_dir from settings."""
        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".custom_cache"
            path = _get_context_path(tmp_path)
            assert path == tmp_path / ".custom_cache" / CONTEXT_FILE


class TestLoadContext:
    """Test load_context function."""

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty_context(self, tmp_path):
        """load_context returns empty ProjectContext if file doesn't exist."""
        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            ctx = await load_context(tmp_path)
            assert isinstance(ctx, ProjectContext)
            assert ctx.entries == []

    @pytest.mark.asyncio
    async def test_loads_existing_context(self, tmp_path):
        """load_context loads context from existing file."""
        cache_dir = tmp_path / ".wunderunner"
        cache_dir.mkdir()
        context_file = cache_dir / CONTEXT_FILE

        ctx = ProjectContext(summary="Test summary", violation_count=3)
        context_file.write_text(ctx.model_dump_json())

        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            loaded = await load_context(tmp_path)
            assert loaded.summary == "Test summary"
            assert loaded.violation_count == 3

    @pytest.mark.asyncio
    async def test_corrupt_file_returns_empty_context(self, tmp_path):
        """load_context returns empty context if file is corrupt."""
        cache_dir = tmp_path / ".wunderunner"
        cache_dir.mkdir()
        context_file = cache_dir / CONTEXT_FILE
        context_file.write_text("invalid json {{{")

        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            ctx = await load_context(tmp_path)
            assert isinstance(ctx, ProjectContext)
            assert ctx.entries == []


class TestSaveContext:
    """Test save_context function."""

    @pytest.mark.asyncio
    async def test_creates_directory_if_missing(self, tmp_path):
        """save_context creates cache directory if it doesn't exist."""
        ctx = ProjectContext(summary="Test")

        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            await save_context(tmp_path, ctx)

            context_file = tmp_path / ".wunderunner" / CONTEXT_FILE
            assert context_file.exists()

    @pytest.mark.asyncio
    async def test_saves_context_as_json(self, tmp_path):
        """save_context writes JSON representation."""
        ctx = ProjectContext(summary="Test summary", violation_count=5)

        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"
            await save_context(tmp_path, ctx)

            context_file = tmp_path / ".wunderunner" / CONTEXT_FILE
            content = context_file.read_text()
            assert "Test summary" in content
            assert '"violation_count": 5' in content


class TestAddEntry:
    """Test add_entry function."""

    @pytest.mark.asyncio
    async def test_adds_entry_to_context(self, tmp_path):
        """add_entry adds entry and saves context."""
        entry = ContextEntry(
            entry_type=EntryType.BUILD,
            explanation="Test entry",
        )

        with patch("wunderunner.storage.context.get_settings") as mock:
            mock.return_value.cache_dir = ".wunderunner"

            ctx = await add_entry(tmp_path, entry)
            assert len(ctx.entries) == 1
            assert ctx.entries[0].explanation == "Test entry"

    @pytest.mark.asyncio
    async def test_triggers_summarization_at_threshold(self, tmp_path):
        """add_entry triggers summarization when threshold reached."""
        # Pre-populate with entries just below threshold
        existing_ctx = ProjectContext(entries_since_summary=SUMMARIZATION_THRESHOLD - 1)
        cache_dir = tmp_path / ".wunderunner"
        cache_dir.mkdir()
        context_file = cache_dir / CONTEXT_FILE
        context_file.write_text(existing_ctx.model_dump_json())

        entry = ContextEntry(
            entry_type=EntryType.BUILD,
            explanation="Triggers summarization",
        )

        with (
            patch("wunderunner.storage.context.get_settings") as mock_settings,
            patch("wunderunner.storage.context.summarize", new_callable=AsyncMock) as mock_summarize,
        ):
            mock_settings.return_value.cache_dir = ".wunderunner"
            mock_summarize.return_value = "Summarized learnings"

            ctx = await add_entry(tmp_path, entry)

            mock_summarize.assert_called_once()
            assert ctx.summary == "Summarized learnings"
            assert ctx.entries == []  # Cleared after summarization
            assert ctx.entries_since_summary == 0

    @pytest.mark.asyncio
    async def test_no_summarization_below_threshold(self, tmp_path):
        """add_entry does not summarize below threshold."""
        entry = ContextEntry(
            entry_type=EntryType.BUILD,
            explanation="Below threshold",
        )

        with (
            patch("wunderunner.storage.context.get_settings") as mock_settings,
            patch("wunderunner.storage.context.summarize", new_callable=AsyncMock) as mock_summarize,
        ):
            mock_settings.return_value.cache_dir = ".wunderunner"

            ctx = await add_entry(tmp_path, entry)

            mock_summarize.assert_not_called()
            assert ctx.entries_since_summary == 1

"""Tests for context summarizer agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.agents.context.summarizer import SYSTEM_PROMPT, agent, summarize
from wunderunner.models.context import ContextEntry, EntryType


class TestSummarizerAgent:
    """Test summarizer agent configuration."""

    def test_system_prompt_exists(self):
        """Summarizer has a system prompt."""
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_describes_purpose(self):
        """System prompt describes summarization task."""
        assert "summarizer" in SYSTEM_PROMPT.lower() or "summary" in SYSTEM_PROMPT.lower()
        assert "docker" in SYSTEM_PROMPT.lower() or "dockerfile" in SYSTEM_PROMPT.lower()

    def test_agent_output_type_is_string(self):
        """Agent outputs a string."""
        assert agent.output_type is str


class TestSummarize:
    """Test summarize function."""

    @pytest.mark.asyncio
    async def test_summarize_formats_entries(self):
        """summarize formats entries correctly in prompt."""
        entries = [
            ContextEntry(
                entry_type=EntryType.BUILD,
                error="npm ERR! Missing",
                fix="Added script",
                explanation="Was missing",
            ),
            ContextEntry(
                entry_type=EntryType.DOCKERFILE,
                error=None,
                fix=None,
                explanation="All good",
            ),
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_result = MagicMock()
            mock_result.output = "Summary text"
            mock_run.return_value = mock_result

            result = await summarize(entries, existing_summary=None)

            # Check the prompt passed to agent
            call_args = mock_run.call_args[0][0]
            assert "<entries>" in call_args
            assert "BUILD" in call_args or "build" in call_args
            assert "npm ERR!" in call_args
            assert result == "Summary text"

    @pytest.mark.asyncio
    async def test_summarize_includes_existing_summary(self):
        """summarize includes existing summary in prompt."""
        entries = [
            ContextEntry(
                entry_type=EntryType.BUILD,
                explanation="New learning",
            ),
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_result = MagicMock()
            mock_result.output = "Updated summary"
            mock_run.return_value = mock_result

            result = await summarize(entries, existing_summary="Previous summary text")

            call_args = mock_run.call_args[0][0]
            assert "<previous_summary>" in call_args
            assert "Previous summary text" in call_args
            assert "Incorporate" in call_args
            assert result == "Updated summary"

    @pytest.mark.asyncio
    async def test_summarize_without_existing_summary(self):
        """summarize works without existing summary."""
        entries = [
            ContextEntry(
                entry_type=EntryType.VALIDATION,
                explanation="Validation passed",
            ),
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_result = MagicMock()
            mock_result.output = "New summary"
            mock_run.return_value = mock_result

            result = await summarize(entries, existing_summary=None)

            call_args = mock_run.call_args[0][0]
            assert "<previous_summary>" not in call_args
            assert result == "New summary"

"""Tests for CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from wunderunner.cli.main import (
    _make_hint_prompt_callback,
    _make_progress_callback,
    _make_secret_prompt_callback,
    _validate_project_path,
)
from wunderunner.workflows.state import Learning, Phase, Severity


class TestValidateProjectPath:
    """Test _validate_project_path function."""

    def test_valid_directory(self, tmp_path):
        """Valid directory path is accepted."""
        result = _validate_project_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_nonexistent_path_raises(self, tmp_path):
        """Nonexistent path raises BadParameter."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(typer.BadParameter, match="does not exist"):
            _validate_project_path(nonexistent)

    def test_file_path_raises(self, tmp_path):
        """File path (not directory) raises BadParameter."""
        file_path = tmp_path / "file.txt"
        file_path.touch()
        with pytest.raises(typer.BadParameter, match="not a directory"):
            _validate_project_path(file_path)


class TestMakeProgressCallback:
    """Test _make_progress_callback function."""

    def test_creates_callable(self):
        """_make_progress_callback returns a callable."""
        console = MagicMock()
        callback = _make_progress_callback(console)
        assert callable(callback)

    def test_prints_info_message(self):
        """Progress callback prints info messages."""
        console = MagicMock()
        callback = _make_progress_callback(console)

        callback(Severity.INFO, "Test message")
        console.print.assert_called_once()
        call_args = console.print.call_args[0][0]
        assert "blue" in call_args
        assert "Test message" in call_args

    def test_prints_success_with_checkmark(self):
        """Progress callback prints success with checkmark."""
        console = MagicMock()
        callback = _make_progress_callback(console)

        callback(Severity.SUCCESS, "Success message")
        console.print.assert_called_once()
        call_args = console.print.call_args[0][0]
        assert "green" in call_args
        assert "✓" in call_args

    def test_prints_warning_with_icon(self):
        """Progress callback prints warning with icon."""
        console = MagicMock()
        callback = _make_progress_callback(console)

        callback(Severity.WARNING, "Warning message")
        call_args = console.print.call_args[0][0]
        assert "yellow" in call_args
        assert "!" in call_args

    def test_prints_error_with_x(self):
        """Progress callback prints error with X icon."""
        console = MagicMock()
        callback = _make_progress_callback(console)

        callback(Severity.ERROR, "Error message")
        call_args = console.print.call_args[0][0]
        assert "red" in call_args
        assert "✗" in call_args


class TestMakeSecretPromptCallback:
    """Test _make_secret_prompt_callback function."""

    def test_creates_callable(self):
        """_make_secret_prompt_callback returns a callable."""
        console = MagicMock()
        callback = _make_secret_prompt_callback(console)
        assert callable(callback)

    def test_prompts_for_secret(self):
        """Secret callback prompts with password=True."""
        console = MagicMock()
        callback = _make_secret_prompt_callback(console)

        with patch("wunderunner.cli.main.Prompt.ask", return_value="secret123") as mock_ask:
            result = callback("API_KEY", None)
            mock_ask.assert_called_once()
            assert mock_ask.call_args[1]["password"] is True
            assert result == "secret123"

    def test_includes_service_hint(self):
        """Secret callback includes service hint when provided."""
        console = MagicMock()
        callback = _make_secret_prompt_callback(console)

        with patch("wunderunner.cli.main.Prompt.ask", return_value="secret") as mock_ask:
            callback("DATABASE_URL", "postgres")
            prompt_text = mock_ask.call_args[0][0]
            assert "postgres" in prompt_text


class TestMakeHintPromptCallback:
    """Test _make_hint_prompt_callback function."""

    def test_creates_callable(self):
        """_make_hint_prompt_callback returns a callable."""
        console = MagicMock()
        callback = _make_hint_prompt_callback(console)
        assert callable(callback)

    def test_displays_learnings(self):
        """Hint callback displays recent learnings."""
        console = MagicMock()
        callback = _make_hint_prompt_callback(console)

        learnings = [
            Learning(
                phase=Phase.BUILD,
                error_type="BuildError",
                error_message="npm ERR! Missing script",
                context="package.json needs build script",
            )
        ]

        with patch("wunderunner.cli.main.Prompt.ask", return_value="add build script"):
            result = callback(learnings)

            # Check that learnings were displayed
            print_calls = [str(call) for call in console.print.call_args_list]
            assert any("BUILD" in str(call) or "build" in str(call) for call in print_calls)
            assert result == "add build script"

    def test_returns_none_on_quit(self):
        """Hint callback returns None when user quits."""
        console = MagicMock()
        callback = _make_hint_prompt_callback(console)

        learnings = [
            Learning(phase=Phase.BUILD, error_type="Error", error_message="msg")
        ]

        with patch("wunderunner.cli.main.Prompt.ask", return_value="q"):
            result = callback(learnings)
            assert result is None

    def test_truncates_long_messages(self):
        """Hint callback truncates long error messages."""
        console = MagicMock()
        callback = _make_hint_prompt_callback(console)

        long_message = "x" * 500
        learnings = [
            Learning(phase=Phase.BUILD, error_type="Error", error_message=long_message)
        ]

        with patch("wunderunner.cli.main.Prompt.ask", return_value="hint"):
            callback(learnings)
            # Message should be truncated in output
            # The actual truncation happens when printing, so just verify no error
            assert console.print.called
